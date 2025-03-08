import re
from typing import List, Optional

from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["piaotia.com", "www.piaotia.com"])
class PiaotianDownloader(BaseBookDownloader):

    name = "piaotian"
    request_delay = 0.75
    source_language = "Chinese"
    enable_book_info_translation = True


    def _extract_book_id(self, url: str) -> Optional[str]:
        match = re.search(r"bookinfo/(\d+)/(\d+).html", url)
        if match:
            category_id, book_id = match.groups()
            return f"{category_id}/{book_id}"

    def _get_chapters(self) -> List[str]:
        url = f"https://www.piaotia.com/html/{self.book_id}"
        soup = self._get_page(url)

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

    def _download_chapter_content(self, chapter_url: str) -> Optional[str]:
        soup = self._get_page(chapter_url)
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
        title_tag = soup.find('h1')
        if title_tag:
            return title_tag.get_text(strip=True)
        return ''

    def _extract_author(self, soup: BeautifulSoup) -> str:
        author_td = soup.find('td', string=re.compile(r'作[\s\xa0]*者'))
        if author_td:
            text = author_td.get_text(strip=True)
            match = re.search(r'作[\s\xa0]*者：[\s\xa0]*(.+)', text)
            if match:
                return match.group(1).strip()
        return ''

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        # Locate the td element that contains the cover image
        td = soup.find('td', attrs={'width': '80%', 'valign': 'top'})
        if not td:
            return ''

        img_tag = td.find('img')
        if not img_tag:
            return ''

        src = img_tag.get('src')
        return src if src else ''
