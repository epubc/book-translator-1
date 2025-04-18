import re
from typing import List, Optional
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from text_processing.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["cn.ttkan.co", "www.ttkan.co"]) # Register for both domains if needed
class TTKanDownloader(BaseBookDownloader):

    name = "ttkan"
    bulk_download = True
    concurrent_downloads = 50
    request_delay = 1
    source_language = "Chinese"
    enable_book_info_translation = True

    def _extract_book_id(self, url: str) -> str:
        """
        Extracts the book identifier from the TTKan URL.
        Example: https://cn.ttkan.co/novel/chapters/xianni-ergen -> xianni-ergen
        """
        parsed_url = urlparse(url)
        match = re.search(r'/novel/chapters/([^/]+)', parsed_url.path)
        if match:
            return match.group(1)

        parts = parsed_url.path.strip('/').split('/')
        if len(parts) > 0:
             potential_id = parts[-1]
             if not potential_id.endswith('.html'): # Basic check
                 return potential_id
        raise ValueError(f"Could not extract book ID from TTKan URL: {url}")

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extracts the book title using the specific og:novel:book_name meta tag."""
        meta_tag = soup.find("meta", attrs={"name": "og:novel:book_name"})
        if not meta_tag:
             meta_tag = soup.find("meta", property="og:title")
        if not meta_tag:
             title_tag = soup.find("title")
             if title_tag and title_tag.string:
                 title_text = title_tag.string.strip()
                 match = re.search(r"《(.*?)》", title_text)
                 if match:
                     return match.group(1)
                 return title_text.split(' ')[0]
             return ''

        # Process found meta tag
        if meta_tag and meta_tag.get("content"):
            title_text = meta_tag["content"].strip()
            # Clean if it's from og:title like "《仙逆》小说 - 天天看小说"
            match = re.search(r"《(.*?)》", title_text)
            if match:
                return match.group(1)
            return title_text.split(' ')[0]

        return '' # Default empty string

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extracts the author name using the og:novel:author meta tag."""
        meta_tag = soup.find("meta", attrs={"name": "og:novel:author"})
        return meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ''

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        """Extracts the cover image URL using the og:image meta tag."""
        meta_tag = soup.find("meta", attrs={"name": "og:image"})
        if not meta_tag:
             meta_tag = soup.find("meta", property="og:image")
        return meta_tag["content"].strip() if meta_tag and meta_tag.get("content") else ''

    def _get_chapters(self) -> List[str]:
        """
        Extracts all chapter links from the hidden 'full_chapters' div on the index page.
        """

        index_url = f"https://cn.ttkan.co/novel/chapters/{self.book_id}"
        soup = self._get_page(index_url)

        if not soup:
            return []

        chapters = []
        # The HTML provided contains a div with all chapters, hidden by default
        full_chapters_div = soup.find("div", class_="full_chapters")

        if not full_chapters_div:
            # Attempt fallback using the initially visible list (might be incomplete)
            list_container = soup.find("amp-list", id="chapters_list")
            if list_container:
                 full_chapters_div = list_container
            else:
                 return [] # Return empty if primary and fallback method fails

        # Find all anchor tags within the target div
        chapter_links = full_chapters_div.find_all("a", href=True)

        parsed_index_url = urlparse(index_url)
        base_url = f"{parsed_index_url.scheme}://{parsed_index_url.netloc}"

        for link in chapter_links:
            href = link["href"]
            if href.startswith("http"):
                continue
            absolute_url = urljoin(base_url, href)
            chapters.append(absolute_url)

        return chapters

    def _download_chapter_content(self, chapter_url: str) -> Optional[str]:
        """
        Downloads and extracts the text content of a chapter from its URL,
        adapted for the ttkan.co / wa01.com structure.
        """
        soup = self._get_page(chapter_url)
        if not soup:
            print(f"Failed to get soup object for {chapter_url}")
            return None

        # Find the main content container div by its class
        content_div = soup.find('div', class_='content')
        if not content_div:
            print(f"Could not find content div with class 'content' on {chapter_url}")
            return None

        # Optional but good practice: Remove any script tags within the content div
        for script in content_div.find_all("script"):
            script.decompose()

        # Find all paragraph tags within the content div
        paragraphs = content_div.find_all('p')
        if not paragraphs:
            print(f"Could not find any <p> tags within the content div on {chapter_url}")
            return None

        chapter_lines = [p.get_text(strip=True) for p in paragraphs]


        full_text = "\n".join(chapter_lines)

        return preprocess_downloaded_text(full_text)
