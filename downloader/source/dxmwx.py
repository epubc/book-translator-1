import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["www.dxmwx.org"])
class DXMWXDownloader(BaseBookDownloader):

    name = "dxmwx"
    bulk_download = True
    concurrent_downloads = 50
    request_delay = 1
    source_language = "Chinese"
    enable_book_info_translation = True


    def _extract_book_id(self, url: str) -> str:
        match = re.search(r"book/(\d+).html", url)
        if not match:
            raise ValueError("Invalid book URL format")
        return match.group(1)

    def _get_chapters(self) -> List[str]:
        """Extract chapter links from the book page."""
        url = f"https://www.dxmwx.org/chapter/{self.book_id}.html"
        soup = self._get_page(self.session, url)

        if not soup:
            return []

        chapters = []

        chapter_divs = soup.find_all("div", style=lambda s: s and "height:40px; line-height:40px;" in s)

        for div in chapter_divs:
            span_elements = div.find_all("span")
            for span in span_elements:
                a_tag = span.find("a")
                if a_tag and a_tag.get("href"):
                    chapters.append(a_tag["href"])

        return [href if href.startswith("http") else f"https://www.dxmwx.org{href}" for href in chapters]


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

        # Try to find content in the Lab_Contents div (based on provided HTML)
        content_div = soup.find('div', id='Lab_Contents')

        # If not found, try the original structure (acontent div)
        if not content_div:
            content_div = soup.find('div', id='acontent', class_='acontent')

        # If still not found, try the alternative structure (articlebody > content)
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
            # If no paragraphs found, try getting text directly
            text = content_div.get_text(strip=True)
            if not text:
                return None
            return preprocess_downloaded_text(text)

        text = "\n".join(p.get_text(strip=True) for p in paragraphs)
        return preprocess_downloaded_text(text)


    def _extract_title(self, soup: BeautifulSoup) -> str:
        meta_title = soup.find("meta", property="og:novel:book_name")
        if meta_title:
            return meta_title.get("content", "").strip()
        return ''

    def _extract_author(self, soup: BeautifulSoup) -> str:
        meta_author = soup.find("meta", property="og:novel:author")
        if meta_author:
            return meta_author.get("content", "").strip()
        return ''

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        meta_cover = soup.find("meta", property="og:image")
        if meta_cover:
            return meta_cover.get("content", "").strip()
        return ''

