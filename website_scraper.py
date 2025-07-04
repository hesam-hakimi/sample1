from typing import Tuple

import requests
from bs4 import BeautifulSoup


class WebsiteScraper:
    """Simple scraper that returns the page content and title for a given URL."""
    def __init__(self, url: str) -> None:
        self.url = url
        self.content = ""
        self.title = ""
        self._fetch()

    def _fetch(self) -> None:
        """Retrieve the page and store the cleaned content and title."""
        response = requests.get(self.url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        self.title = (
            soup.title.string.strip() if soup.title and soup.title.string else ""
        )
        self.content = soup.get_text(separator="\n").strip()

    def fetch(self) -> Tuple[str, str]:
        """Return the content and title previously fetched."""
        return self.content, self.title
