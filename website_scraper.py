from typing import Tuple

import requests
from bs4 import BeautifulSoup


class WebsiteScraper:
    """Simple scraper that returns the page content and title for a given URL."""
    def __init__(self, url: str) -> None:
        self.url = url

    def fetch(self) -> Tuple[str, str]:
        """Fetch the URL and return a tuple of (content, title)."""
        response = requests.get(self.url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string.strip() if soup.title and soup.title.string else ''
        content = soup.get_text(separator='\n')
        return content, title
