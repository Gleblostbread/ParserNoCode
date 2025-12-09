from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.exceptions import HTTPException
from fastapi.params import Body, Query
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator
from typing import Annotated, Dict, List
from selectolax.parser import HTMLParser
import httpx


app = FastAPI()

class SelectorCSS(BaseModel):
    query: str
    all: bool | None = None
    order: int | None = None
    strip: bool = True

    @model_validator(mode='after')
    def one_of_all_and_order(self):
        if self.all is not None and self.order is not None:
            raise ValueError('Choose one of all or order')
        return self



class ScrapeBody(BaseModel):
    url: HttpUrl
    selectors: Dict[str, SelectorCSS]




@app.get('/')
def get_start_page() -> HTMLResponse:
    with open('base.html') as page:
        base_page = page.read()
    
    return HTMLResponse(base_page)


@app.post('/scrape')
def scrape(query: Annotated[ScrapeBody, Body()]):
    try:
        page = httpx.get(str(query.url))
    except httpx.HTTPError:
        return HTTPException(422, detail='Page for parse not found')
    
    parser = HTMLParser(page.text)
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
