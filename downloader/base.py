import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from abc import ABC, abstractmethod
import time
import json

import httpx
from httpx_retry import RetryTransport, RetryPolicy
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from platformdirs import user_data_path

from config.models import GEMINI_FLASH_THINKING_MODEL_CONFIG
from text_processing.text_processing import sanitize_path_name
from translator.manager import TranslationManager, PromptStyle


exponential_retry = (
    RetryPolicy()
    .with_max_retries(3)
    .with_min_delay(0.5)
    .with_multiplier(2)
    .with_retry_on(lambda status_code: status_code >= 400)
)

@dataclass
class BookInfo:
    id: str
    title: str
    author: str
    source_url: str
    cover_img: str

    def __init__(self, id: str, title:str, author:str, source_url:str, cover_img:str = None):
        self.id = id
        self.title = title
        self.author = author
        self.source_url = source_url
        self.cover_img = cover_img

    def to_dict(self) -> Dict[str, Any]:
        return {
            key: value for key, value in self.__dict__.items()
            if value is not None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BookInfo':
        return cls(**{
            key: value for key, value in data.items()
            if key in cls.__annotations__
        })


class StateManager:
    def __init__(self):
        self._app_data_dir = user_data_path("BookDownloader", ensure_exists=True) # Example app name
        self._state_mapping_file = self._app_data_dir / "book_state_locations.json"
        self._mapping: Dict[str, str] = self._load_mapping()
        self._initialized = True

    def _create_key(self, output_dir: Path, url: str) -> str:
        # Use a separator unlikely to appear in paths or URLs
        return f"{output_dir.resolve().as_posix()}||{url}"

    def _load_mapping(self) -> Dict[str, str]:
        if self._state_mapping_file.exists() and self._state_mapping_file.is_file():
            try:
                with open(self._state_mapping_file, 'r', encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    else:
                        logging.warning(f"State mapping file '{self._state_mapping_file}' "
                                        f"does not contain a valid dictionary. Loading empty.")
                        return {}
            except json.JSONDecodeError:
                logging.warning(f"Error decoding JSON from '{self._state_mapping_file}'. "
                                f"File might be corrupt. Loading empty.")
                return {}
            except IOError as e:
                logging.warning(f"Could not read state mapping file '{self._state_mapping_file}': {e}. "
                                f"Loading empty.")
                return {}
            except Exception as e:
                logging.warning(f"An unexpected error occurred loading '{self._state_mapping_file}': {e}. "
                                f"Loading empty.")
                return {}
        return {}

    def save_mapping(self):
        try:
            with open(self._state_mapping_file, 'w', encoding="utf-8") as f:
                json.dump(self._mapping, f, indent=4, ensure_ascii=False)
        except IOError as e:
            logging.error(f"Could not write state mapping to '{self._state_mapping_file}': {e}")
        except TypeError as e:
            logging.error(f"Could not serialize state mapping data: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred saving state mapping: {e}")

    def get_state_file_path(self, output_dir: Path, url: str) -> Optional[str]:
        key = self._create_key(output_dir, url)
        return self._mapping.get(key)

    def set_state_file_path(self, output_dir: Path, url: str, state_file_path: Path):
        key = self._create_key(output_dir, url)
        abs_path = state_file_path.resolve().as_posix()
        if self._mapping.get(key) != abs_path:
             self._mapping[key] = abs_path
             self.save_mapping()


class BaseBookDownloader(ABC):
    name = ""
    bulk_download = False
    concurrent_downloads = 1
    request_delay = 0
    source_language = ""
    enable_book_info_translation = False
    timeout = 1

    def __init__(self, output_dir: Path, url: str, start_chapter:Optional[int] = None, end_chapter:Optional[int] = None):
        self.url = url
        self.output_dir = output_dir.resolve() # Use resolved path
        self.book_id = self._extract_book_id(url)
        self._state_lock = threading.Lock()
        self.stop_flag = False
        self.start_chapter = start_chapter
        self.end_chapter = end_chapter
        self.client = self._init_http_client()
        self.translator = TranslationManager(
            model_config=GEMINI_FLASH_THINKING_MODEL_CONFIG,
        )
        self.state_manager = StateManager()
        self.book_dir: Optional[Path] = None # Will be set during initialization
        self.book_info: Optional[BookInfo] = None # Will be set during initialization
        self.state = self._load_state()

        if not self.state:
            self._initialize_book()
        else:
            # Ensure book_info and book_dir are loaded from state
            self.book_info = BookInfo.from_dict(self.state.get('book_info', {}))
            if self.book_info and self.book_info.title:
                 # Reconstruct book_dir path based on loaded info
                 self.book_dir = self.output_dir / f"{self.__class__.name}/{sanitize_path_name(self.book_info.title)}"
                 self.book_dir.mkdir(parents=True, exist_ok=True)
            else:
                # Handle case where state exists but book_info is missing/incomplete
                logging.warning("State loaded but book_info missing or incomplete. Re-initializing.")
                self._initialize_book()


    def stop(self) -> None:
        with self._state_lock:
            self.stop_flag = True
        if self.client:
            self.client.close()
        logging.info("Stop request received. Download will halt.")

    def _init_http_client(self) -> httpx.Client:
        client = httpx.Client(
            transport=RetryTransport(policy=exponential_retry),
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self._random_user_agent(),
                "Accept-Language": "en-US,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
            }
        )
        return client

    def download_book(self) -> None:
        if not self.book_dir or not self.book_info:
             logging.error("Book information not properly initialized. Cannot download.")
             return

        if self.bulk_download:
            self._download_concurrently()
        else:
            self._download_sequentially()

    def _download_concurrently(self) -> None:
        if 'chapter_urls' not in self.state:
            logging.error("Chapter URLs not found in state. Cannot download concurrently.")
            return

        chapter_urls = self.state['chapter_urls']
        download_status = self.state.get('download_status', {}) # Use get for safety

        unprocessed = [
            (idx, url)
            for idx, url in enumerate(chapter_urls, start=1)
            if (self.start_chapter is None or idx >= self.start_chapter)
            and (self.end_chapter is None or idx <= self.end_chapter)
            and download_status.get(str(idx)) != "completed"
        ]

        if not unprocessed:
            logging.info("No chapters to download or all chapters in range are already completed.")
            return

        logging.info(f"Starting concurrent download for {len(unprocessed)} chapters.")
        batch_size = self.concurrent_downloads
        for i in range(0, len(unprocessed), batch_size):
            if self.stop_flag:
                logging.info("Download stopped gracefully during concurrent processing.")
                break
            batch = unprocessed[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {
                    executor.submit(self._process_chapter, chapter_num, url): chapter_num
                    for chapter_num, url in batch
                }
                for future in as_completed(futures):
                    if self.stop_flag: # Check again after each future completes
                        break
                    chapter_num = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"Chapter {chapter_num} failed processing: {str(e)}", exc_info=True)
                        with self._state_lock:
                            # Ensure download_status exists
                            if 'download_status' not in self.state:
                                self.state['download_status'] = {}
                            self.state['download_status'][str(chapter_num)] = "failed"
                            self._save_state() # Save state on failure

            if not self.stop_flag and self.request_delay > 0:
                time.sleep(self.request_delay)

    def _download_sequentially(self) -> None:
        if 'chapter_urls' not in self.state:
            logging.error("Chapter URLs not found in state. Cannot download sequentially.")
            return

        chapter_urls = self.state['chapter_urls']
        download_status = self.state.get('download_status', {}) # Use get for safety

        logging.info("Starting sequential download.")
        for chapter_num, url in enumerate(chapter_urls, start=1):
            if self.stop_flag:
                logging.info("Download stopped gracefully during sequential processing.")
                break

            if self.start_chapter is not None and chapter_num < self.start_chapter:
                continue
            if self.end_chapter is not None and chapter_num > self.end_chapter:
                logging.info("Reached end chapter limit.")
                break
            if download_status.get(str(chapter_num)) == "completed":
                logging.debug(f"Skipping already completed chapter {chapter_num}")
                continue

            logging.info(f"Processing chapter {chapter_num}...")
            self._process_chapter(chapter_num, url)

            if not self.stop_flag and self.request_delay > 0:
                time.sleep(self.request_delay)

    def _process_chapter(self, chapter_num: int, chapter_url: str) -> None:
        if self.stop_flag:
            logging.debug(f"Stop flag set. Skipping chapter {chapter_num}.")
            return

        content = self._download_chapter_with_retry(chapter_url)

        with self._state_lock:
            if self.stop_flag: # Check again before saving state
                return

            # Ensure download_status exists before modification
            if 'download_status' not in self.state:
                self.state['download_status'] = {}

            if content:
                self._save_chapter(chapter_num, content)
                self.state['download_status'][str(chapter_num)] = "completed"
                self._save_state()
            else:
                logging.error(f"Permanent failure processing chapter {chapter_num} from {chapter_url}")
                self.state['download_status'][str(chapter_num)] = "failed"
                self._save_state() # Save state even on failure

    def _download_chapter_with_retry(self, chapter_url: str) -> Optional[str]:
        try:
            content = self._download_chapter_content(chapter_url)
            if content:
                return content
            logging.warning(f"Empty content received for {chapter_url} after successful download.")
            return None # Return None for empty but successful downloads
        except httpx.RequestError as e:
            # Handled by retry transport, but log if it ultimately fails
            logging.error(f"Final request error after retries for {chapter_url}: {str(e)}")
            return None
        except httpx.HTTPStatusError as e:
            # Handled by retry transport, but log if it ultimately fails
            logging.error(f"Final HTTP status error {e.response.status_code} after retries for {chapter_url}")
            return None
        except Exception as e:
            # Catch other potential errors during content extraction
            logging.error(f"Unexpected error downloading/processing chapter {chapter_url}: {str(e)}", exc_info=True)
            return None

    def _initialize_book(self) -> None:
        logging.info(f"Initializing book from URL: {self.url}")
        try:
            self.book_info = self._get_book_info()
            if not self.book_info.title or not self.book_info.author:
                 raise ValueError("Failed to extract mandatory book title or author.")

            if self.enable_book_info_translation:
                logging.info("Translating book title and author...")
                self.book_info.title = self.translator.translate_text(self.book_info.title, prompt_style=PromptStyle.BookInfo)
                self.book_info.author = self.translator.translate_text(self.book_info.author, prompt_style=PromptStyle.BookInfo)
                logging.info(f"Translated Title: {self.book_info.title}, Author: {self.book_info.author}")


            self.book_dir = self.output_dir / f"{self.__class__.name}/{sanitize_path_name(self.book_info.title)}"
            self.book_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"Book directory set to: {self.book_dir}")

            logging.info("Downloading cover image...")
            self.book_info.cover_img = self._get_image_path(self.book_info.cover_img) # Stores path or empty string

            logging.info("Fetching chapter list...")
            chapter_urls = self._get_chapters()
            if not chapter_urls:
                 raise ValueError("Failed to retrieve chapter list.")
            logging.info(f"Found {len(chapter_urls)} chapters.")

            # Update state atomically
            with self._state_lock:
                 self._update_state(
                    book_info=self.book_info.to_dict(),
                    chapter_urls=chapter_urls,
                    download_status={} # Initialize empty download status
                 )
                 self._save_state() # Save initial state

        except Exception as e:
            logging.error(f"Failed to initialize book: {e}", exc_info=True)
            # Reset critical attributes if initialization fails partway
            self.book_info = None
            self.book_dir = None
            self.state = {} # Clear potentially partial state
            raise # Re-raise the exception to signal failure


    def _get_page(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = self.client.get(url, follow_redirects=True)
            response.raise_for_status()
            # Detect encoding, fallback to utf-8
            encoding = response.encoding or 'utf-8'
            return BeautifulSoup(response.content, "html.parser", from_encoding=encoding)
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logging.error(f"HTTP error fetching page: {url}, exception: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error fetching page: {url}, exception: {e}", exc_info=True)
            return None

    def _get_book_info(self) -> BookInfo:
        soup = self._get_page(self.url)
        if not soup:
            raise ValueError(f"Failed to fetch or parse book page: {self.url}")

        title = self._extract_title(soup)
        author = self._extract_author(soup)
        cover_src = self._extract_cover_img(soup)

        if not title: logging.warning(f"Could not extract title from {self.url}")
        if not author: logging.warning(f"Could not extract author from {self.url}")
        if not cover_src: logging.warning(f"Could not extract cover image source from {self.url}")

        return BookInfo(
            id=self.book_id,
            title=title or "Unknown Title",
            author=author or "Unknown Author",
            source_url=self.url,
            cover_img=cover_src or '',
        )

    def _save_chapter(self, chapter_number: int, content: str) -> None:
        if not self.book_dir:
            logging.error("Book directory not set, cannot save chapter.")
            return

        chapters_dir = self.book_dir / "input_chapters"
        chapters_dir.mkdir(exist_ok=True)

        filename = chapters_dir / f"chapter_{chapter_number:04d}.txt"
        try:
            filename.write_text(content, encoding="utf-8")
            logging.info(f"Saved chapter {chapter_number} to {filename}")
        except IOError as e:
            logging.error(f"Failed to save chapter {chapter_number} to {filename}: {str(e)}")
        except Exception as e:
             logging.error(f"Unexpected error saving chapter {chapter_number}: {str(e)}", exc_info=True)


    def _load_state(self) -> Dict[str, Any]:
        state_file_path_str = self.state_manager.get_state_file_path(self.output_dir, self.url)
        if state_file_path_str:
            state_file = Path(state_file_path_str)
            if state_file.exists() and state_file.is_file():
                try:
                    with open(state_file, 'r', encoding="utf-8") as f:
                        state_data = json.load(f)
                        logging.info(f"Loaded existing state from {state_file}")
                        return state_data
                except json.JSONDecodeError:
                    logging.error(f"Corrupted state file {state_file}, initializing fresh state.")
                    return {}
                except IOError as e:
                    logging.error(f"Could not read state file {state_file}: {e}. Initializing fresh state.")
                    return {}
                except Exception as e:
                     logging.error(f"Unexpected error loading state file {state_file}: {e}. Initializing fresh state.", exc_info=True)
                     return {}
            else:
                 logging.warning(f"State file path found ({state_file}) but file doesn't exist or is not a file. Initializing fresh state.")
                 return {}
        else:
             logging.info("No existing state found for this book and output directory.")
             return {}


    def _save_state(self) -> None:
        if not self.book_dir:
            logging.error("Book directory not set. Cannot save state.")
            return

        state_file = self.book_dir / "state.json"
        # Ensure the directory exists before trying to write the file
        self.book_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Make a copy for safe serialization
            state_to_save = self.state.copy()
            # Convert defaultdict to regular dict if present
            if 'download_status' in state_to_save and isinstance(state_to_save['download_status'], defaultdict):
                 state_to_save['download_status'] = dict(state_to_save['download_status'])

            with open(state_file, 'w', encoding="utf-8") as f:
                json.dump(state_to_save, f, indent=2, ensure_ascii=False)
            # Update the central mapping
            self.state_manager.set_state_file_path(self.output_dir, self.url, state_file)
            logging.debug(f"Saved state to {state_file}")

        except IOError as e:
            logging.error(f"Failed to save state to {state_file}: {str(e)}")
        except TypeError as e:
            logging.error(f"Failed to serialize state data for saving: {e} - State: {state_to_save}")
        except Exception as e:
             logging.error(f"Unexpected error saving state to {state_file}: {str(e)}", exc_info=True)

    def _update_state(self, **kwargs) -> None:
        # No lock needed here as it's called within locked sections (_initialize_book, _process_chapter)
        self.state.update(kwargs)

    def _get_image_path(self, src: str) -> str:
        if not src or not self.book_dir:
            return ''

        # Create a safe filename from the URL or use a default name
        try:
            img_filename = Path(src).name
            if not img_filename or len(img_filename) > 100: # Basic sanity check
                img_filename = "cover"
            # Ensure it ends with a common image extension if possible, default to jpg
            img_ext = Path(img_filename).suffix.lower()
            if img_ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                 img_filename += ".jpg"

            image_path = self.book_dir / sanitize_path_name(img_filename)
        except Exception:
            logging.warning("Could not determine image filename, using default.")
            image_path = self.book_dir / "cover.jpg"


        if image_path.exists():
            logging.info(f"Cover image already exists at {image_path}. Skipping download.")
            return image_path.resolve().as_posix()

        try:
            logging.info(f"Attempting to download cover image from: {src}")
            response = self.client.get(src)
            response.raise_for_status()

            # Ensure the directory exists
            self.book_dir.mkdir(parents=True, exist_ok=True)

            with open(image_path, 'wb') as f:
                f.write(response.content)
            logging.info(f"Saved cover image to {image_path}")
            return image_path.resolve().as_posix()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logging.error(f"HTTP error downloading cover image from {src}: {e}")
            return ''
        except IOError as e:
            logging.error(f"IO error saving cover image to {image_path}: {e}")
            return ''
        except Exception as e:
            logging.error(f"Unexpected error downloading/saving cover image {src}: {e}", exc_info=True)
            return ''

    def _random_user_agent(self) -> str:
        try:
            return UserAgent().random
        except Exception: # Catch potential errors from fake-useragent
             logging.warning("Failed to get random User-Agent. Using a default.")
             return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"


    @abstractmethod
    def _extract_book_id(self, url: str) -> str:
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
        pass

    @abstractmethod
    def _download_chapter_content(self, chapter_url: str) -> Optional[str]:
        pass
