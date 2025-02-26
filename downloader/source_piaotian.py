import logging
import re
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader, BookInfo
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["piaotia.com"])
class PiaotianDownloader(BaseBookDownloader):

    request_delay = 0.5
    source_language = "Chinese"
    enable_book_info_translation = True


    def _extract_book_id(self, url: str) -> str:
        match = re.search(r"bookinfo/(\d+)/(\d+).html", url)
        if match:
            category_id, book_id = match.groups()
            return f"{category_id}/{book_id}"

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
        url = f"https://piaotia.com/html/{self.book_id}"
        soup = self._get_page(self.session, url)

        if not soup:
            return []

        chapters = []
        centent_div = soup.find("div", class_="centent")
        if centent_div:
            ul_elements = centent_div.find_all("ul")
            for ul in ul_elements:
                li_elements = ul.find_all("li")
                for li in li_elements:
                    a_tag = li.find("a")
                    if a_tag and a_tag.get("href"):  # Check if <a> exists and has href
                        chapters.append(a_tag["href"])

        return [f"{url}/{chapter}" for chapter in chapters]

    def _download_chapter_content(self, session: requests.Session, chapter_url: str) -> Optional[str]:
        soup = self._get_page(session, chapter_url)
        if not soup:
            return None

        for tag in soup(["script", "style"]):
            tag.decompose()

        # Extract and clean the text.
        raw_text = soup.get_text(separator="\n")
        content_text = self._extract_content_text(raw_text)

        return preprocess_downloaded_text(content_text)


    def _extract_content_text(self, text: str, start_marker="返回书页", end_marker="（快捷键  ←）") -> Optional[str]:
        # Split the text into non-empty, stripped lines.
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Try to locate the start and end markers.
        start_index = next((i for i, line in enumerate(lines) if start_marker in line), None)
        end_index = next((i for i, line in enumerate(lines) if end_marker in line), None)

        # Determine the slice of lines based on the markers.
        if start_index is not None and end_index is not None and start_index < end_index:
            relevant_lines = lines[start_index + 1: end_index]
        elif start_index is not None:
            relevant_lines = lines[start_index + 1:]
        elif end_index is not None:
            relevant_lines = lines[:end_index]
        else:
            relevant_lines = lines

        return "\n".join(relevant_lines)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        text = soup.find('title').get_text(strip=True)
        parts = text.split("-")
        return parts[0].strip("《》") if parts else "Unknown Title"

    def _extract_author(self, soup: BeautifulSoup) -> str:
        text = soup.find('title').get_text(strip=True)
        parts = text.split("-")
        return parts[1].strip() if len(parts) > 1 else "Unknown Author"


    def _get_page(self, session: requests.Session, url: str) -> Optional[BeautifulSoup]:
        try:
            response = session.get(url, timeout=5)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logging.error(f"Error fetching page: {url}", exc_info=True)
            return None
