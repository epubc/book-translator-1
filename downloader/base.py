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
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from fake_useragent import UserAgent

from config import settings


@dataclass
class BookInfo:
    """Structured representation of book metadata."""
    id: str
    title: str
    author: str
    source_url: str

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
    bulk_download = False  # Default to sequential
    concurrent_downloads = 1
    request_delay = 0
    source_language = ""
    should_translate_book_info = False


    def __init__(self, output_dir: Path, url: str):
        self.url = url
        self.book_id = self._extract_book_id(url)
        self.book_dir = output_dir / f"book_{self.book_id}"
        self.book_dir.mkdir(parents=True, exist_ok=True)
        self._state_lock = threading.Lock()


        self.bulk_download = self.__class__.bulk_download
        self.concurrent_downloads = self.__class__.concurrent_downloads
        self.request_delay = self.__class__.request_delay
        self.source_language = self.__class__.source_language
        self.should_translate_book_info = self.__class__.should_translate_book_info

        self.session = self._init_requests_session()

        # Load state and initialize
        self.state = self._load_state()
        if not self.state:
            self._initialize_book()
        else:
            self.book_info = BookInfo.from_dict(self.state.get('book_info', {}))

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

        # Filter unprocessed chapters with their original indices
        unprocessed = [
            (idx, url)
            for idx, url in enumerate(chapter_urls, start=1)
            if download_status.get(str(idx))  !="completed"
        ]

        batch_size = self.concurrent_downloads
        for i in range(0, len(unprocessed), batch_size):
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
            # Wait for a while after processing each batch
            time.sleep(self.request_delay)

    def _download_sequentially(self) -> None:
        """Sequential download implementation."""
        chapter_urls = self.state['chapter_urls']
        download_status = self.state.get('download_status', {})

        for chapter_num, url in enumerate(chapter_urls, start=1):
            if download_status.get(str(chapter_num)) == "completed":
                continue

            self._process_chapter(chapter_num, url)
            time.sleep(self.request_delay)

    def _process_chapter(self, chapter_num: int, chapter_url: str) -> None:
        """Common processing for both download modes."""
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
        chapter_urls = self._get_chapters()

        self._update_state(
            book_info=self.book_info.to_dict(),
            chapter_urls=chapter_urls,
            download_status={}
        )
        self._save_state()

    def _save_chapter(self, chapter_number: int, content: str) -> None:
        """Save chapter content to file."""
        chapters_dir = self.book_dir / "downloaded_chapters"
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

    def _random_user_agent(self) -> str:
        """Generate a random user agent for requests."""
        return UserAgent().random

    def stop(self):
        """
        Stops the download process.  This method should be called from another thread
        (like the TranslationThread).
        """
        print("EightXSKDownloader stop() called")  # Debugging print
        self._stop_requested = True

    @abstractmethod
    def _extract_book_id(self, url: str) -> str:
        """Extract book ID from URL (to be implemented by child classes)."""
        pass

    @abstractmethod
    def _get_book_info(self) -> BookInfo:
        """Extract book metadata (to be implemented by child classes)."""
        pass

    @abstractmethod
    def _get_chapters(self) -> List[str]:
        """Retrieve list of chapter URLs (to be implemented by child classes)."""
        pass

    @abstractmethod
    def _download_chapter_content(self, session: requests.Session, chapter_url: str) -> Optional[str]:
        """Download and process chapter content (to be implemented by child classes)."""
        pass
