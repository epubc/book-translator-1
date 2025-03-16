import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


@DownloaderFactory.register(domains=["langrenxiaoshuo.com", "www.langrenxiaoshuo.com"])
class LangrenxiaoshuoDownloader(BaseBookDownloader):
    """Book downloader for langrenxiaoshuo.com."""

    name = "langrenxiaoshuo"
    request_delay = 1.0
    source_language = "Chinese"
    enable_book_info_translation = True

    def _extract_book_id(self, url: str) -> str:
        """Extract the book ID from the URL."""
        match = re.search(r'html/([^/]+)/?', url)
        if match:
            return match.group(1)
        return ""

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract the book title from the page."""
        meta_title = soup.find('meta', property='og:novel:book_name')
        if meta_title and meta_title.get('content'):
            return meta_title.get('content')
        
        h1_title = soup.find('h1')
        if h1_title:
            return h1_title.text.strip()
            
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.text.strip()
            if '_' in title_text:
                return title_text.split('_')[0].strip()
            return title_text
            
        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract the book author from the page."""
        meta_author = soup.find('meta', property='og:novel:zuozhe')
        if meta_author and meta_author.get('content'):
            return meta_author.get('content')
            
        author_p = soup.find('p', string=re.compile(r'作\s*者'))
        if author_p:
            text = author_p.text.strip()
            match = re.search(r'作\s*者：\s*(.+)', text)
            if match:
                return match.group(1).strip()
                
        return ""

    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        """Extract the book cover image from the page."""
        meta_image = soup.find('meta', property='og:image')
        if meta_image and meta_image.get('content'):
            img_src = meta_image.get('content')
            if img_src.startswith('/'):
                return f"https://www.langrenxiaoshuo.com{img_src}"
            return img_src
            
        img_div = soup.find('div', class_='imgbox')
        if img_div:
            img_tag = img_div.find('img')
            if img_tag and img_tag.get('src'):
                img_src = img_tag.get('src')
                if img_src.startswith('/'):
                    return f"https://www.langrenxiaoshuo.com{img_src}"
                return img_src
                
        return ""

    def _get_chapters(self) -> List[str]:
        """Get all chapter URLs for the book."""
        soup = self._get_page(self.url)
        if not soup:
            return []
            
        chapter_links = []
        
        section_divs = soup.find_all('div', class_='section-box')
        
        if len(section_divs) >= 2:
            section_div = section_divs[1]
            
            links = section_div.find_all('a')
            for link in links:
                href = link.get('href')
                if href and 'html' in href:
                    if href.startswith('http'):
                        chapter_links.append(href)
                    else:
                        chapter_links.append(urljoin("https://www.langrenxiaoshuo.com", href))
        
        return chapter_links

    def _download_chapter_content(self, chapter_url: str) -> Optional[str]:
        """Download and extract chapter content."""
        soup = self._get_page(chapter_url)
        if not soup:
            return None
            
        # Remove unnecessary elements
        for tag in soup(['script', 'style', 'iframe', 'ins', 'a']):
            tag.decompose()
            
        # Try to find the content div
        content_div = soup.find('div', id='content')
        
        # If the specific content div is not found, try a more general approach
        if not content_div:
            # Look for the main content area
            content_div = soup.find('div', class_='content')
            
        # If still not found, try another common pattern
        if not content_div:
            # Try to find a div with a relevant class that might contain the content
            for div in soup.find_all('div'):
                if div.has_attr('class') and any(c in ['article', 'text', 'body', 'main'] for c in div.get('class', [])):
                    content_div = div
                    break
        
        # If all else fails, extract text from the body
        if not content_div:
            content_div = soup.find('body')
            
        if not content_div:
            return None
            
        # Extract the text
        text = content_div.get_text('\n')
        
        # Clean the text
        cleaned_text = self._clean_chapter_text(text, chapter_url)
        
        return preprocess_downloaded_text(cleaned_text)
        
    def _clean_chapter_text(self, text: str, chapter_url: str) -> str:
        """Clean the chapter text by removing irrelevant content."""
        # Split into lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        
        # Try to find title
        chapter_title = ""
        for line in lines[:10]:  # Check first few lines for chapter title
            if '章' in line or '第' in line:
                chapter_title = line
                break
                
        # Find starting markers
        start_idx = 0
        for i, line in enumerate(lines):
            # Skip empty lines and navigation text
            if not line or any(marker in line.lower() for marker in ['上一章', '下一章', '目录', '章节']):
                continue
                
            # If we found a potential chapter title, start from there
            if chapter_title and line == chapter_title:
                start_idx = i
                break
                
            # Otherwise just use the first substantive line
            start_idx = i
            break
            
        # Find ending markers
        end_idx = len(lines)
        for i in range(len(lines) - 1, 0, -1):
            if any(marker in lines[i].lower() for marker in ['上一章', '下一章', '目录', '章节', '请记住本站', '关注我们']):
                end_idx = i
                break
                
        # Extract the relevant content
        relevant_lines = lines[start_idx:end_idx]
        
        if not relevant_lines:
            return ""
            
        # Join the content lines
        content = '\n'.join(relevant_lines)
        
        # Add chapter URL for reference
        content = f"{chapter_url}\n\n{content}"
        
        return content 