import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import time
import json

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from fake_useragent import UserAgent

from config import settings
from translator.core import Translator, PromptStyle


@dataclass
class BookInfo:
    """Structured representation of book metadata."""
    id: str
    title: str
    author: str
    source_url: str
    cover_img: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert BookInfo to dictionary for serialization."""
        return {
            key: value for key, value in self.__dict__.items()
            if value is not None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BookInfo':
        """Create BookInfo instance from dictionary."""
        return cls(**{
            key: value for key, value in data.items()
            if key in cls.__annotations__
        })


class BaseBookDownloader(ABC):
    """Base class for downloading books from various sources."""

    # Class-level default configurations
    name = ""
    bulk_download = False  # Default to sequential
    concurrent_downloads = 1
    request_delay = 0
    source_language = ""
    enable_book_info_translation = False

    def __init__(self, output_dir: Path, url: str, start_chapter:Optional[int] = None, end_chapter:Optional[int] = None):
        self.url = url
        self.book_id = self._extract_book_id(url)
        self.book_dir = output_dir / f"{self.__class__.name}/book_{self.book_id}"
        self.book_dir.mkdir(parents=True, exist_ok=True)
        self._state_lock = threading.Lock()
        self.stop_flag = False

        # Store start_chapter and end_chapter as instance variables
        self.start_chapter = start_chapter
        self.end_chapter = end_chapter

        self.session = self._init_requests_session()
        self.translator = Translator()

        # Load state and initialize
        self.state = self._load_state()
        if not self.state:
            self._initialize_book()
        else:
            self.book_info = BookInfo.from_dict(self.state.get('book_info', {}))


    def stop(self) -> None:
        """Gracefully stop the download process."""
        with self._state_lock:
            self.stop_flag = True

    def _init_requests_session(self) -> requests.Session:
        """Initialize a new session with current settings."""
        session = requests.Session()
        retry = Retry(
            total=settings.DOWNLOAD_MAX_RETRIES,
            backoff_factor=self.request_delay,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.headers.update({
            "User-Agent": self._random_user_agent(),
            "Accept-Language": "en-US,en;q=0.5",
        })
        return session

    def download_book(self) -> None:
        """Main download entry point with mode selection."""
        if self.bulk_download:
            self._download_concurrently()
        else:
            self._download_sequentially()

    def _download_concurrently(self) -> None:
        """Parallel download implementation."""
        chapter_urls = self.state['chapter_urls']
        download_status = self.state.get('download_status', defaultdict(str))

        # Filter unprocessed chapters within the specified range
        unprocessed = [
            (idx, url)
            for idx, url in enumerate(chapter_urls, start=1)
            if (self.start_chapter is None or idx >= self.start_chapter)
            and (self.end_chapter is None or idx <= self.end_chapter)
            and download_status.get(str(idx)) != "completed"
        ]

        if not unprocessed:
            logging.info("No chapters to download in the specified range.")
            return

        batch_size = self.concurrent_downloads
        for i in range(0, len(unprocessed), batch_size):
            if self.stop_flag:
                logging.info("Download stopped gracefully.")
                break
            batch = unprocessed[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {
                    executor.submit(self._process_chapter, chapter_num, url): chapter_num
                    for chapter_num, url in batch
                }
                for future in as_completed(futures):
                    chapter_num = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"Chapter {chapter_num} failed: {str(e)}")
                        with self._state_lock:
                            self.state['download_status'][str(chapter_num)] = "failed"
                            self._save_state()
            time.sleep(self.request_delay)

    def _download_sequentially(self) -> None:
        """Sequential download implementation."""
        chapter_urls = self.state['chapter_urls']
        download_status = self.state.get('download_status', {})

        for chapter_num, url in enumerate(chapter_urls, start=1):
            # Skip chapters before start_chapter
            if self.start_chapter is not None and chapter_num < self.start_chapter:
                continue
            # Stop after end_chapter
            if self.end_chapter is not None and chapter_num > self.end_chapter:
                break
            # Skip already completed chapters
            if download_status.get(str(chapter_num)) == "completed":
                continue

            self._process_chapter(chapter_num, url)
            time.sleep(self.request_delay)

    def _process_chapter(self, chapter_num: int, chapter_url: str) -> None:
        """Common processing for both download modes."""
        if self.stop_flag:
            logging.debug(f"Stop flag set. Skipping chapter {chapter_num}.")
            return

        content = self._download_chapter_with_retry(chapter_url)

        with self._state_lock:
            if content:
                self._save_chapter(chapter_num, content)
                self.state['download_status'][str(chapter_num)] = "completed"
                self._save_state()
            else:
                logging.error(f"Permanent failure on chapter {chapter_num}")
                self.state['download_status'][str(chapter_num)] = "failed"
                self._save_state()

    def _download_chapter_with_retry(self, chapter_url: str) -> Optional[str]:
        """Retry logic with subclass-configurable delays."""
        for attempt in range(1, settings.DOWNLOAD_MAX_RETRIES + 1):
            if self.stop_flag:
                return None
            session = self._init_requests_session()
            try:
                content = self._download_chapter_content(session, chapter_url)
                if content:
                    return content
            except Exception as e:
                logging.warning(f"Attempt {attempt} failed: {str(e)}")
                delay = self.request_delay ** attempt
                time.sleep(delay)
            finally:
                session.close()
        return None

    def _initialize_book(self):
        """Fetch initial book info and chapter list."""
        self.book_info = self._get_book_info()
        if self.enable_book_info_translation:
            self.book_info.title = self.translator.translate_text(self.book_info.title, prompt_style=PromptStyle.BookInfo)
            self.book_info.author = self.translator.translate_text(self.book_info.author, prompt_style=PromptStyle.BookInfo)

        chapter_urls = self._get_chapters()

        self._update_state(
            book_info=self.book_info.to_dict(),
            chapter_urls=chapter_urls,
            download_status={}
        )
        self._save_state()

    def _get_page(self, session: requests.Session, url: str) -> Optional[BeautifulSoup]:
        try:
            response = session.get(url, timeout=5)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logging.error(f"Error fetching page: {url}, exception: {e}", exc_info=True)
            return None


    def _get_book_info(self) -> BookInfo:
        soup = self._get_page(self.session, self.url)
        if not soup:
            raise ValueError("Failed to fetch book page")

        title = self._extract_title(soup)
        author = self._extract_author(soup)
        cover_src = self._extract_cover_img(soup)
        cover_img = self._get_image_path(cover_src)
        return BookInfo(
            id=self.book_id,
            title=title,
            author=author,
            source_url=self.url,
            cover_img=cover_img,
        )

    def _save_chapter(self, chapter_number: int, content: str) -> None:
        """Save chapter content to file."""
        chapters_dir = self.book_dir / "input_chapters"
        chapters_dir.mkdir(exist_ok=True)

        filename = chapters_dir / f"chapter_{chapter_number:04d}.txt"
        try:
            filename.write_text(content, encoding="utf-8")
            logging.info(f"Saved chapter {chapter_number} to {filename}")
        except IOError as e:
            logging.error(f"Failed to save chapter {chapter_number}: {str(e)}")

    def _load_state(self) -> Dict[str, Any]:
        """Load state from file."""
        state_file = self.book_dir / "state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logging.error("Corrupted state file, initializing fresh state")
                return {}
        return {}

    def _save_state(self) -> None:
        """Save current state to file."""
        state_file = self.book_dir / "state.json"
        try:
            with open(state_file, 'w', encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logging.error(f"Failed to save state: {str(e)}")

    def _update_state(self, **kwargs) -> None:
        """Update the current state."""
        self.state.update(kwargs)

    def _get_image_path(self, src: str) -> str:
        # Define the path to save the cover image
        image_path = self.book_dir / "cover.jpg"

        # Attempt to download and save the image
        try:
            response = self.session.get(src, timeout=2)
            if response.status_code == 200:
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                return image_path.as_posix()
            else:
                return ''
        except Exception as e:
            print(f"Error downloading cover image: {e}")
            return ''

    def _random_user_agent(self) -> str:
        """Generate a random user agent for requests."""
        return UserAgent().random

    @abstractmethod
    def _extract_book_id(self, url: str) -> str:
        """Extract book ID from URL (to be implemented by child classes)."""
        pass

    @abstractmethod
    def _extract_title(self, soup: BeautifulSoup) -> str:
        pass

    @abstractmethod
    def _extract_author(self, soup: BeautifulSoup) -> str:
        pass

    @abstractmethod
    def _extract_cover_img(self, soup: BeautifulSoup) -> str:
        pass

    @abstractmethod
    def _get_chapters(self) -> List[str]:
        """Retrieve list of chapter URLs (to be implemented by child classes)."""
        pass

    @abstractmethod
    def _download_chapter_content(self, session: requests.Session, chapter_url: str) -> Optional[str]:
        """Download and process chapter content (to be implemented by child classes)."""
        pass