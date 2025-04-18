import re
from typing import List, Optional

from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from text_processing.text_processing import preprocess_downloaded_text


GARBLE_MAP = {
    "大": "小", "多": "少", "上": "下", "左": "右", "前": "后",
    "冷": "热", "高": "低", "进": "退", "黑": "白", "天": "地",
    "男": "女", "里": "外", "死": "活", "公": "私", "快": "慢",
    "宽": "窄", "强": "弱", "轻": "重", "缓": "急", "松": "紧",
    "好": "坏", "美": "丑", "善": "恶", "闲": "忙", "来": "去",
    "分": "合", "存": "亡", "动": "静", "浓": "淡", "偏": "正",
    "饥": "饱", "爱": "恨", "升": "降", "开": "关", "始": "终",
    "胖": "瘦", "迎": "送", "盈": "亏", "真": "假", "虚": "实",
    "有": "无", "雅": "俗", "是": "否", "稀": "密", "粗": "细",
    "东": "西",
    "你": "我",
    # Add the reverse mappings
    "小": "大", "少": "多", "下": "上", "右": "左", "后": "前",
    "热": "冷", "低": "高", "退": "进", "白": "黑", "地": "天",
    "女": "男", "外": "里", "活": "死", "私": "公", "慢": "快",
    "窄": "宽", "弱": "强", "重": "轻", "急": "缓", "紧": "松",
    "坏": "好", "丑": "美", "恶": "善", "忙": "闲", "去": "来",
    "合": "分", "亡": "存", "静": "动", "淡": "浓", "正": "偏",
    "饱": "饥", "恨": "爱", "降": "升", "关": "开", "终": "始",
    "瘦": "胖", "送": "迎", "亏": "盈", "假": "真", "实": "虚",
    "无": "有", "俗": "雅", "否": "是", "密": "稀", "细": "粗",
    "西": "东",
    "我": "你"
}

def reverse_garble(text: str) -> str:
    """Reverses the character swapping."""
    return "".join(GARBLE_MAP.get(char, char) for char in text)


@DownloaderFactory.register(domains=["quanben.io", "www.quanben.io"])
class QuanbenDownloader(BaseBookDownloader):

    name = "quanben"
    bulk_download = True
    concurrent_downloads = 50
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
        Downloads and extracts the content of a novel chapter from quanben.io,
        handling specific cleaning and anti-scraping reversal.

        Args:
            chapter_url: The URL of the chapter to download

        Returns:
            The preprocessed text content of the chapter, or None if extraction failed
        """
        soup = self._get_page(chapter_url)
        if not soup:
            print("Failed to get page soup.")
            return None

        article_body = soup.find('div', class_='articlebody')
        if not article_body:
            print("Could not find 'div.articlebody'.")
            return None

        content_div = article_body.find('div', id='content')
        if not content_div:
            print("Could not find 'div#content' within 'div.articlebody'.")
            return None

        # 1. Remove unwanted elements (scripts, ads) BEFORE processing paragraphs
        for element in content_div.find_all(["script", "div"]):
            # More general removal of divs, assuming ads are the primary divs to remove
            # or specific ad classes if known e.g. class_='ads'
            if 'class' in element.attrs and 'ads' in element.attrs['class']:
                element.decompose()
            elif element.name == 'script':
                element.decompose()

        # 2. Extract paragraphs and process them
        paragraphs = content_div.find_all('p')
        if not paragraphs:
            print("No paragraphs found within 'div#content'.")
            # Check if content might be directly in content_div without <p> tags
            raw_text = content_div.get_text(separator='\n', strip=True)
            if raw_text:
                print("Found raw text in content_div, returning that.")
                # No paragraph-based reversal possible here, just return cleaned text
                return preprocess_downloaded_text(raw_text)
            return None  # No paragraphs and no raw text

        processed_paragraphs = []
        # The JS garbles based on the index in the *full* list of <p> tags *found by JS*.
        # However, the sample HTML shows garbling *after* the ad divs.
        # Let's assume the index applies to the paragraphs *within the content div* after cleanup.
        content_paragraph_index = 1
        for p in paragraphs[1:]:
            p_text = p.get_text(strip=True)

            # Skip empty paragraphs
            if not p_text:
                continue

            # Skip specific warning paragraphs
            if p_text.startswith("【您看到这段文字") or p_text.startswith("【请到源网页阅读"):
                continue

            # Skip the specific '...' placeholder potentially added by JS (though unlikely to be in raw source)
            if p_text == "...":
                continue

            if content_paragraph_index >= 10 and content_paragraph_index % 2 == 0:
                p_text = reverse_garble(p_text)  # Apply reversal


            processed_paragraphs.append(p_text)
            content_paragraph_index += 1  # Increment index for the *next* valid content paragraph

        if not processed_paragraphs:
            print("No valid content paragraphs extracted after filtering.")
            return None

        final_text = "\n".join(processed_paragraphs)
        return preprocess_downloaded_text(final_text)

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

