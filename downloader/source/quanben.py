import re
from typing import List, Optional

from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from text_processing.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["quanben.io", "www.quanben.io"])
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

    def _get_chapters(self) -> List[str]:
        """Extract chapter links from the book page and generate all URLs between first and last."""
        url = f"https://quanben.io/n/{self.book_id}/list.html"
        soup = self._get_page(url)

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


    def _download_chapter_content(self, chapter_url: str) -> Optional[str]:
        """
        Downloads and extracts the content of a novel chapter from the specified URL.

        Args:
            chapter_url: The URL of the chapter to download

        Returns:
            The preprocessed text content of the chapter, or None if extraction failed
        """
        soup = self._get_page(chapter_url)
        if not soup:
            return None

        article_body = soup.find('div', class_='articlebody')
        content_div = article_body.find('div', id='content')

        if not content_div:
            return None

        # Remove all script tags and ad divs
        for element in content_div.find_all(["script", "div"], class_=lambda c: c == "ads" if c else False):
            element.decompose()

        # Extract text from paragraphs
        paragraphs = content_div.find_all('p')
        if not paragraphs:
            return None

        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
        return preprocess_downloaded_text(text)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        return soup.find('h3').get_text(strip=True)

    def _extract_author(self, soup: BeautifulSoup) -> str:
        return soup.find('span', itemprop="author").get_text(strip=True)

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        img_tag = soup.find('img', itemprop="image")
        if not img_tag:
            return ''

        src = img_tag.get('src')
        return src if src else ''

