import re
import time
import logging
from pathlib import Path
from typing import List, Optional

from selenium import webdriver
from selenium_stealth import stealth
import undetected_chromedriver as uc
from fake_useragent import UserAgent
from bs4 import BeautifulSoup

from downloader.base import BaseBookDownloader
from downloader.factory import DownloaderFactory
from translator.text_processing import preprocess_downloaded_text


# @DownloaderFactory.register(domains=["8xsk.cc", "8xbook.cc"])
class EightXSKSeleniumDownloader(BaseBookDownloader):
    """
    Downloads books from 8xsk.cc website, using a hybrid approach:
    - Selenium for the main book page to bypass Cloudflare protection
    - Regular requests for all other pages (chapter lists, chapter content) for better performance
    """
    name = "8xsk_selenium"
    request_delay = 0.5
    source_language = "Chinese"
    enable_book_info_translation = True
    
    # Selenium-specific settings
    INITIAL_PAGE_LOAD_DELAY = 5.0  # Longer wait for main book page (Cloudflare challenge)
    MAX_CHAPTER_LIST_PAGES = 100  # Maximum pages to check for chapter lists
    
    def __init__(self, output_dir: Path, url: str, start_chapter: Optional[int] = None, end_chapter: Optional[int] = None):
        """
        Initialize the hybrid 8xsk downloader.
        
        Args:
            output_dir: Directory to save downloaded content
            url: The book URL to download from
            start_chapter: Optional chapter to start from (1-indexed)
            end_chapter: Optional chapter to end at (1-indexed)
        """
        # Driver will be created only when needed for main page
        self.driver = None
        self.cookies_transferred = False
        
        # Call parent __init__ with required arguments
        super().__init__(output_dir=output_dir, url=url, start_chapter=start_chapter, end_chapter=end_chapter)
        
        logging.info(f"Initialized hybrid downloader for URL: {url}")

    
    def _create_selenium_driver(self) -> webdriver.Chrome:
        """
        Creates and configures a Selenium WebDriver instance with undetected-chromedriver and stealth.
        Only called when needed for Cloudflare bypass.
        
        Returns:
            webdriver.Chrome: Configured Selenium WebDriver instance.
            
        Raises:
            RuntimeError: If driver creation fails
        """
        try:
            logging.info("Creating Selenium WebDriver for 8xsk Cloudflare bypass...")
            options = uc.ChromeOptions()
            # options.add_argument('--headless')  # Keep headless for background execution
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            # User-Agent rotation for added anonymity
            user_agent = UserAgent().random
            logging.info(f"Using User-Agent: {user_agent}")
            options.add_argument(f"user-agent={user_agent}")
            
            # Create the driver with explicit path if ChromeDriver is giving issues
            driver = uc.Chrome(options=options, use_subprocess=False)
            
            logging.info("Applying stealth settings to WebDriver...")
            # Apply stealth settings to further evade detection
            stealth(
                driver,
                languages=["en-US", "en"],
                vendor="Google Inc.",
                platform="Win32",
                webgl_vendor="Intel Inc.",
                renderer="Intel Iris OpenGL Engine",
                fix_hairline=True,
            )
            
            logging.info("Selenium WebDriver created successfully")
            return driver
        except Exception as e:
            error_msg = f"Failed to create Selenium WebDriver: {e}"
            logging.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    def _fetch_main_page_with_selenium(self, url: str) -> Optional[BeautifulSoup]:
        """
        Uses Selenium to fetch the main book page and bypass Cloudflare.
        Also transfers cookies to the requests session for subsequent requests.
        
        Args:
            url: The main book page URL
            
        Returns:
            Optional[BeautifulSoup]: Parsed HTML content or None if failed
        """
        # Lazy-initialize the driver only when needed
        if self.driver is None:
            self.driver = self._create_selenium_driver()
        
        try:
            logging.info(f"Fetching main page with Selenium: {url}")
            self.driver.get(url)
            
            # Wait for Cloudflare challenge to be solved
            logging.info(f"Waiting for Cloudflare challenge: {self.INITIAL_PAGE_LOAD_DELAY}s")
            time.sleep(self.INITIAL_PAGE_LOAD_DELAY)
            
            # Check if page still has Cloudflare challenge
            page_source = self.driver.page_source
            if "Checking if the site connection is secure" in page_source or "Just a moment" in page_source:
                logging.warning("Cloudflare challenge still active, waiting longer...")
                time.sleep(self.INITIAL_PAGE_LOAD_DELAY * 2)
                page_source = self.driver.page_source
            
            # Transfer cookies from Selenium to requests session for future requests
            if not self.cookies_transferred:
                self._transfer_cookies_to_requests()
                self.cookies_transferred = True
            
            return BeautifulSoup(page_source, "html.parser")
        
        except Exception as e:
            logging.error(f"Error fetching main page with Selenium: {e}")
            return None
    
    def _transfer_cookies_to_requests(self) -> None:
        """Transfer cookies from Selenium to the requests session."""
        if self.driver:
            try:
                selenium_cookies = self.driver.get_cookies()
                for cookie in selenium_cookies:
                    self.session.cookies.set(
                        cookie['name'], 
                        cookie['value'], 
                        domain=cookie.get('domain', '')
                    )
                logging.info(f"Transferred {len(selenium_cookies)} cookies to requests session")
            except Exception as e:
                logging.error(f"Failed to transfer cookies: {e}")
    
    def _fetch_page_with_requests(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch a page using regular requests (for chapter lists and content).
        
        Args:
            url: The URL to fetch
            
        Returns:
            Optional[BeautifulSoup]: Parsed HTML content or None if failed
        """
        try:
            logging.info(f"Fetching with requests: {url}")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Pause to avoid rate limiting
            time.sleep(self.request_delay)
            
            return BeautifulSoup(response.text, "html.parser")
        except Exception as e:
            logging.error(f"Error fetching with requests: {url} - {e}")
            return None
    
    def _extract_book_id(self, url: str) -> str:
        """Extract book ID from the book URL."""
        match = re.search(r"book/(\d+).html", url)
        if not match:
            raise ValueError("Invalid book URL format")
        return match.group(1)
    
    def _get_chapters(self) -> List[str]:
        """
        Retrieves chapter URLs from the paginated chapter list using regular requests.
        
        Returns:
            List of chapter URLs
        """
        base_url = f"https://8xsk.cc/book/{self.book_id}_"
        chapter_links = []
        last_chapter_info = None  # For detecting duplicate content
        
        logging.info(f"Starting chapter list retrieval for book ID: {self.book_id}")
        
        for page_num in range(1, self.MAX_CHAPTER_LIST_PAGES + 1):
            page_url = f"{base_url}{page_num}.html"
            logging.info(f"Fetching chapter list page {page_num}: {page_url}")
            
            try:
                # Use regular requests for chapter list pages
                soup = self._fetch_page_with_requests(page_url)
                if not soup:
                    logging.warning(f"Failed to fetch page {page_url}, stopping pagination")
                    break
                
                # Try multiple different selectors for chapter list (site sometimes changes)
                chapter_info = None
                for selector in ["dl.index#jieqi_page_contents", "dl#jieqi_page_contents", "dl.index"]:
                    chapter_info = soup.select_one(selector)
                    if chapter_info:
                        break
                        
                if not chapter_info:
                    logging.warning(f"No chapter list found on page {page_url}, stopping pagination")
                    break
                
                # Check for duplicate content to stop early
                chapter_info_str = str(chapter_info)
                if chapter_info_str == last_chapter_info:
                    logging.info("Duplicate chapter info detected. Stopping page iteration.")
                    break
                    
                last_chapter_info = chapter_info_str
                
                # Extract chapter links
                found_links = 0
                for dd_tag in chapter_info.find_all("dd"):
                    for a_tag in dd_tag.find_all("a"):
                        if a_tag.get("href"):
                            chapter_links.append(a_tag["href"])
                            found_links += 1
                
                logging.info(f"Found {found_links} chapters on page {page_num}")
                
                if found_links == 0:
                    logging.warning(f"No chapter links found on page {page_url}, stopping pagination")
                    break
                
                time.sleep(self.request_delay)
                
            except Exception as e:
                logging.error(f"Error processing chapter list page {page_url}: {e}")
                break
        
        logging.info(f"Total chapters found: {len(chapter_links)}")
        return chapter_links
    
    def _get_page(self, session, url: str, timeout: int = 5) -> Optional[BeautifulSoup]:
        """
        Override _get_page to use Selenium for main book page and requests for others.
        
        Args:
            session: Original session (not used)
            url: URL to fetch
            
        Returns:
            BeautifulSoup object if successful, None otherwise
        """
        # Check if this is the main book page
        if re.search(r"book/\d+\.html$", url):
            # Use Selenium for main book page (Cloudflare bypass)
            return self._fetch_main_page_with_selenium(url)
        else:
            # Use regular requests for all other pages
            return self._fetch_page_with_requests(url)
    
    def _download_chapter_content(self, session, chapter_url: str) -> Optional[str]:
        """
        Downloads the content of a chapter using regular requests.
        
        Args:
            session: Original session (not used)
            chapter_url: URL of the chapter
            
        Returns:
            Preprocessed chapter text if successful, None otherwise
        """
        logging.info(f"Downloading chapter content from {chapter_url} using requests")
        soup = self._fetch_page_with_requests(chapter_url)
        if not soup:
            logging.warning(f"Failed to fetch chapter content from {chapter_url}")
            return None
            
        content_div = soup.find('div', id='acontent', class_='acontent')
        if not content_div:
            return None
            
        # Remove script tags that might contain ads
        for script in content_div.find_all("script"):
            script.decompose()
            
        return preprocess_downloaded_text(content_div.get_text(separator="\n", strip=True))
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract book title from the page."""
        text = soup.find('title').get_text(strip=True)
        parts = text.split("-")
        return parts[0].strip("《》") if parts else ''
    
    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author name from the page."""
        text = soup.find('title').get_text(strip=True)
        parts = text.split("-")
        return parts[1].strip() if parts else ''
    
    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        """Extract cover image URL from the page."""
        img_tag = soup.find('img', class_='cover_l')
        if not img_tag:
            return ''
            
        src = img_tag.get('src')
        return src if src else ''
    
    def stop(self) -> None:
        """Override stop to close the Selenium WebDriver if it exists."""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
                logging.info("Selenium WebDriver closed")
            except Exception as e:
                logging.error(f"Error closing WebDriver: {e}")
        super().stop()
