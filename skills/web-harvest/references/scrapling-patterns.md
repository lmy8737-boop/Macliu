# Scrapling Patterns

Scrapling is an adaptive Python web scraping framework. It supports browser-like HTTP fetching, dynamic browser fetching, stealth fetching, adaptive selectors, sessions, proxies, and Spider crawls.

## Install

```bash
python3 -m pip install --user "scrapling[all]"
scrapling install
```

If only parser/fetcher basics are needed:

```bash
python3 -m pip install --user "scrapling[fetchers]"
scrapling install
```

## Basic Fetcher

Use for public pages where static HTML contains the data.

```python
from scrapling.fetchers import Fetcher, FetcherSession

with FetcherSession(impersonate="chrome") as session:
    page = session.get("https://quotes.toscrape.com/", stealthy_headers=True)
    rows = []
    for quote in page.css(".quote"):
        rows.append({
            "text": quote.css(".text::text").get(),
            "author": quote.css(".author::text").get(),
        })
```

## DynamicFetcher

Use when JavaScript rendering is required and login state is not tied to the user's browser.

```python
from scrapling.fetchers import DynamicSession

with DynamicSession(headless=True, network_idle=True) as session:
    page = session.fetch("https://example.com")
    title = page.css("title::text").get()
```

## StealthyFetcher

Use only for authorized public-data collection where anti-bot pages block normal fetching. Start with a tiny sample and rate-limit aggressively.

```python
from scrapling.fetchers import StealthySession

with StealthySession(headless=True, solve_cloudflare=True) as session:
    page = session.fetch("https://example.com/protected", network_idle=True)
    data = page.css("main").get()
```

## Adaptive Selectors

Use when a site changes layout and previously saved elements need to be relocated.

```python
from scrapling.fetchers import StealthyFetcher

StealthyFetcher.adaptive = True
page = StealthyFetcher.fetch("https://example.com", headless=True, network_idle=True)
items = page.css(".product", auto_save=True)

# Later, after layout changes:
items = page.css(".product", adaptive=True)
```

## Spider Template

Use for multi-page crawls. Always start with a small `start_urls` sample before scaling.

```python
from scrapling.spiders import Spider, Request, Response


class ExampleSpider(Spider):
    name = "example"
    start_urls = ["https://example.com/"]
    concurrent_requests = 4
    download_delay = 1

    async def parse(self, response: Response):
        for item in response.css(".item"):
            yield {
                "title": item.css(".title::text").get(),
                "url": response.urljoin(item.css("a::attr(href)").get()),
            }

        next_href = response.css("a.next::attr(href)").get()
        if next_href:
            yield response.follow(next_href)


if __name__ == "__main__":
    result = ExampleSpider(crawldir="./crawl_data").start()
    result.items.to_jsonl("items.jsonl")
```

## Quality Checks

- Validate selectors on 3-5 pages before bulk crawling.
- Save raw sample HTML or screenshots for debugging when fields are missing.
- Include source URL and crawl timestamp in each record.
- Use JSONL for long runs, CSV for tabular handoff, Markdown for research briefs.
- Respect robots.txt and site terms where applicable.
