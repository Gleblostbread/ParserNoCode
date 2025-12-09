from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from fastapi.exceptions import HTTPException
from fastapi.params import Body, Query

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from typing import Annotated, Dict, List
from selectolax.parser import HTMLParser
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser


class SelectorCSS(BaseModel):
    query: str
    all: bool | None = None
    order: int | None = None
    strip: bool = True

    @model_validator(mode='after')
    def one_of_all_and_order(self):
        if self.all is not None and self.order is not None:
            raise ValueError('Choose one of "all" or "order"')
        return self


class ScrapeBody(BaseModel):
    url: HttpUrl
    selectors: Dict[str, SelectorCSS]



_PLAYWRIGHT = None
_BROWSER = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _PLAYWRIGHT, _BROWSER
    _PLAYWRIGHT = await async_playwright().start()
    _BROWSER = await _PLAYWRIGHT.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",  # важно на машинах с малым /dev/shm
            "--disable-gpu"
        ]
    )
    yield

    await _BROWSER.close()
    await _PLAYWRIGHT.stop()


app = FastAPI(lifespan=lifespan)


async def get_browser() -> Browser:
    if _BROWSER is None:
        raise RuntimeError("Browser not initialized")
    return _BROWSER


@app.get('/')
async def get_start_page() -> HTMLResponse:
    with open('base.html') as page:
        base_page = page.read()
    
    return HTMLResponse(base_page)


@app.post('/scrape')
async def scrape(query: Annotated[ScrapeBody, Body()], browser: Browser = Depends(get_browser)):
    context = await browser.new_context()
    page = await context.new_page()

    try:
        await page.goto(str(query.url), timeout=10000)
        await page.wait_for_load_state("networkidle")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    page_content = await page.content()
    parser = HTMLParser(page_content)
    data = {}
    for name, selector in query.selectors.items():
        if parser.css_matches(selector.query):
            all_matches = parser.css(selector.query)

        else:
            data[name] = None
            continue

        if selector.all:
            data[name] = [node.text(strip=selector.strip) for node in all_matches]
        
        elif selector.order:
            data[name] = all_matches[selector.order].text(strip=selector.strip)

        else:
            data[name] = all_matches[0].text(strip=selector.strip)

    return {"data": data}
