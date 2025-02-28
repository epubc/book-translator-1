import logging
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader, BookInfo
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["quanben.io"])
class QuanbenDownloader(BaseBookDownloader):

    name = "quanben"
    bulk_download = True
    concurrent_downloads = 100
    request_delay = 1
    source_language = "Chinese"
    enable_book_info_translation = True


    def _extract_book_id(self, url: str) -> str:
        match = re.search(r"/([^/]+)/?$", url)
        if not match:
            raise ValueError("Invalid book URL format")
        return match.group(1)

    def _get_book_info(self) -> BookInfo:
        soup = self._get_page(self.session, self.url)
        if not soup:
            raise ValueError("Failed to fetch book page")

        title = self._extract_title(soup)
        author = self._extract_author(soup)

        return BookInfo(
            id=self.book_id,
            title=title,
            author=author,
            source_url=self.url,
        )

    def _get_chapters(self) -> List[str]:
        """Extract chapter links from the book page and generate all URLs between first and last."""
        url = f"https://quanben.io/n/{self.book_id}/list.html"
        soup = self._get_page(self.session, url)

        if not soup:
            return []

        # Extract all chapter links from the list pages
        chapter_links = soup.select("ul.list3 li a[href]")
        if not chapter_links:
            return []

        # Extract chapter numbers from hrefs
        chapters = []
        for link in chapter_links:
            href = link.get("href", "")
            # Split the href to get the chapter number, e.g., '/n/daoguiyixian/1.html' -> 1
            parts = href.strip('/').split('/')
            if not parts:
                continue
            chapter_part = parts[-1].split('.')[0]
            if chapter_part.isdigit():
                chapters.append(int(chapter_part))

        if not chapters:
            return []

        first = min(chapters)
        last = max(chapters)

        # Generate URLs from first to last chapter
        base_url = f"https://quanben.io/n/{self.book_id}/"
        return [f"{base_url}{i}.html" for i in range(first, last + 1)]


    def _download_chapter_content(self, session: requests.Session, chapter_url: str) -> Optional[str]:
        """
        Downloads and extracts the content of a novel chapter from the specified URL.

        Args:
            session: The requests session to use for HTTP requests
            chapter_url: The URL of the chapter to download

        Returns:
            The preprocessed text content of the chapter, or None if extraction failed
        """
        soup = self._get_page(session, chapter_url)
        if not soup:
            return None

        # First try to find content in the acontent div (original method)
        content_div = soup.find('div', id='acontent', class_='acontent')

        # If not found, try the new structure (articlebody > content)
        if not content_div:
            articlebody = soup.find('div', class_='articlebody')
            if articlebody:
                content_div = articlebody.find('div', id='content')

        if not content_div:
            return None

        # Remove all script tags and ad divs
        for element in content_div.find_all(["script", "div"], class_=lambda c: c == "ads" if c else False):
            element.decompose()

        # Extract text from paragraphs
        paragraphs = content_div.find_all('p')
        if not paragraphs:
            return None

        text = "\n\n".join(p.get_text(strip=True) for p in paragraphs)
        return preprocess_downloaded_text(text)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        return soup.find('h3').get_text(strip=True)

    def _extract_author(self, soup: BeautifulSoup) -> str:
        return soup.find('span', itemprop="author").get_text(strip=True)


    def _get_page(self, session: requests.Session, url: str) -> Optional[BeautifulSoup]:
        try:
            response = session.get(url, timeout=5)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logging.error(f"Error fetching page: {url}, exception: {e}", exc_info=True)
            return None
