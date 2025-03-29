import re
import time
from typing import List, Optional

from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["8xsk.cc", "8xbook.cc"])
class EightXSKDownloader(BaseBookDownloader):

    name = "8xsk"
    request_delay = 1
    source_language = "Chinese"
    enable_book_info_translation = True


    def _extract_book_id(self, url: str) -> str:
        match = re.search(r"book/(\d+).html", url)
        if not match:
            raise ValueError("Invalid book URL format")
        return match.group(1)

    def _get_chapters(self) -> List[str]:
        base_url = f"https://8xsk.cc/book/{self.book_id}_"
        page = 1
        chapters = []
        last_chapters = []
        total_page = 100

        while page <= total_page:
            url = f"{base_url}{page}.html"
            soup = self._get_page(url)
            if not soup:
                break

            page_chapters = self._extract_chapters_from_page(soup)
            if not page_chapters or page_chapters == last_chapters:
                break

            last_chapters = page_chapters
            chapters.extend(page_chapters)
            page += 1
            time.sleep(self.request_delay)

        return chapters

    def _download_chapter_content(self, chapter_url: str) -> Optional[str]:
        soup = self._get_page(chapter_url)
        if not soup:
            return None

        content_div = soup.find('div', id='ccontent', class_='ccontent')
        if not content_div:
            return None

        for script in content_div.find_all("script"):
            script.decompose()

        return preprocess_downloaded_text(content_div.get_text(separator="\n", strip=True))

    def _extract_title(self, soup: BeautifulSoup) -> str:
        text = soup.find('title').get_text(strip=True)
        parts = text.split("-")
        return parts[0].strip("《》") if parts else ''

    def _extract_author(self, soup: BeautifulSoup) -> str:
        text = soup.find('title').get_text(strip=True)
        parts = text.split("-")
        return parts[1].strip() if parts else ''

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        img_tag = soup.find('img', class_='cover_l')
        if not img_tag:
            return ''

        src = img_tag.get('src')
        return src if src else ''


    def _extract_chapters_from_page(self, soup: BeautifulSoup) -> List[str]:
        chapter_list = soup.find("dl", id="jieqi_page_contents")
        return [
            a["href"] for dd in chapter_list.find_all("dd", recursive=False)
            if (a := dd.find("a")) and a.get("href")
        ] if chapter_list else []
