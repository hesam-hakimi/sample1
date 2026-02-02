from typing import Tuple

import requests
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts = []
        self.in_title = False
        self.in_p = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self.in_title = True
        elif tag == "p":
            self.in_p = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "p":
            self.in_p = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_p:
            self.text_parts.append(data)

    def get_text(self) -> Tuple[str, str]:
        text = " ".join(self.text_parts)
        return text, self.title


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
        parser = _TextExtractor()
        parser.feed(response.text)
        text, title = parser.get_text()
        self.title = title.strip()
        clean = text.replace("\n", " ").replace("\t", " ")
        self.content = " ".join(clean.split())

    def fetch(self) -> Tuple[str, str]:
        """Return the content and title previously fetched."""
        return self.content, self.title
