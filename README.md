# Website Scraper

This project provides a small `WebsiteScraper` class for retrieving web page content and titles using `requests` and `BeautifulSoup`.

## Installation

Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
```

## Running Tests

Tests are written with `pytest`.

```bash
pytest
```

## Usage Example

```python
from website_scraper import WebsiteScraper

scraper = WebsiteScraper("https://example.com")
print(scraper.title)
print(scraper.content)
```
