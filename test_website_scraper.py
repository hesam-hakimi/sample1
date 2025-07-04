from unittest import mock

import requests

from website_scraper import WebsiteScraper


class MockResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise requests.HTTPError(f"Status {self.status_code}")


def test_fetch_title_and_content():
    html = "<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
    mock_resp = MockResponse(html)
    with mock.patch("requests.get", return_value=mock_resp):
        scraper = WebsiteScraper("http://example.com")
        content, title = scraper.fetch()
        assert title == "Test"
        assert "Hello" in content


def test_cnn_content_clean():
    html = (
        "<html><head><title>CNN</title></head>"
        "<body><p>Breaking\n\tNews</p></body></html>"
    )
    mock_resp = MockResponse(html)
    with mock.patch("requests.get", return_value=mock_resp):
        scraper = WebsiteScraper("https://www.cnn.com")
        content, _ = scraper.fetch()
        assert "\n" not in content
        assert "\t" not in content
