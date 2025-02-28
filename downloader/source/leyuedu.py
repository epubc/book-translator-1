import re
from typing import List, Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["www.22is.com"])
class LeYueDuDownloader(BaseBookDownloader):
    name = "leyuedu"
    bulk_download = True
    concurrent_downloads = 20
    request_delay = 0.5
    source_language = "Chinese"
    enable_book_info_translation = True

    def _extract_book_id(self, url: str) -> str:
        match = re.search(r"/(?:book|read)/(\d+)", url)
        if not match:
            raise ValueError("Invalid book URL format")
        return match.group(1)

    def _get_chapters(self) -> List[str]:
        # Construct chapters URL from original URL
        parsed_url = urlparse(self.url)
        path = parsed_url.path.replace("/book/", "/read/").replace(".html", "")
        chapters_url = urljoin(self.url, f"{path}/")

        soup = self._get_page(self.session, chapters_url)
        if not soup:
            return []

        chapter_links = soup.select("div#catalog ul li a[href]")
        return [urljoin(chapters_url, a["href"]) for a in chapter_links]

    def _download_chapter_content(self, session: requests.Session, chapter_url: str) -> Optional[str]:
        soup = self._get_page(session, chapter_url)
        if not soup:
            return None

        content_div = soup.select_one("div.txtnav")
        if not content_div:
            return None

        # Remove unwanted elements
        for element in content_div.select("h1, div.txtinfo, div#txtright, div.baocuo"):
            element.decompose()

        # Extract text from paragraphs
        paragraphs = content_div.find_all("p")
        if not paragraphs:
            return None

        text = "\n\n".join(p.get_text(strip=True) for p in paragraphs)
        return preprocess_downloaded_text(text)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        title_tag = soup.select_one("div.booknav2 h1 a")
        return title_tag.get_text(strip=True) if title_tag else ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        author_tag = soup.select_one('.booknav2 p a[href*="/author/"]')
        return author_tag.get_text(strip=True) if author_tag else ""

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        cover_tag = soup.select_one("div.bookimg2 img")
        if not cover_tag:
            return ""

        src = cover_tag.get("src", "")
        return urljoin(self.url, src) if src else ""
