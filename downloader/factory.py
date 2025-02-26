import re
from pathlib import Path
from typing import Dict, Type
from urllib.parse import urlparse

from downloader.base import BaseBookDownloader


class DownloaderFactory:
    """Factory class for creating appropriate book downloader instances."""

    _downloaders: Dict[str, Type[BaseBookDownloader]] = {}
    _domain_patterns: Dict[str, Type[BaseBookDownloader]] = {}

    @classmethod
    def register(cls, domains: list[str], pattern: str = None):
        """
        Decorator to register a downloader class with its associated domains.

        Args:
            domains: List of domain names this downloader handles
            pattern: Optional regex pattern for more complex URL matching
        """

        def decorator(downloader_class: Type[BaseBookDownloader]):
            for domain in domains:
                cls._downloaders[domain] = downloader_class
            if pattern:
                cls._domain_patterns[pattern] = downloader_class
            return downloader_class

        return decorator

    @classmethod
    def create_downloader(cls, url: str, output_dir: Path) -> BaseBookDownloader:
        """
        Create appropriate downloader instance based on URL.

        Args:
            url: The book URL to download from
            output_dir: Directory to save downloaded content

        Returns:
            Instance of appropriate BaseBookDownloader subclass

        Raises:
            ValueError: If no suitable downloader is found for the URL
        """
        # Extract domain from URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

        # Remove 'www.' prefix if present
        domain = re.sub(r'^www\.', '', domain)

        # First try exact domain match
        downloader_class = cls._downloaders.get(domain)

        # If no exact match, try pattern matching
        if not downloader_class:
            for pattern, handler in cls._domain_patterns.items():
                if re.search(pattern, url, re.IGNORECASE):
                    downloader_class = handler
                    break

        if not downloader_class:
            raise ValueError(f"No suitable downloader found for URL: {url}")

        return downloader_class(output_dir, url)
