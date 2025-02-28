import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Type, Optional
from urllib.parse import urlparse

from downloader.base import BaseBookDownloader


@dataclass
class SourceInfo:
    """Detailed information about a book source."""
    name: str
    domains: List[str]
    bulk_download: bool
    concurrent_downloads: int
    request_delay: float
    source_language: str
    download_speed: float  # chapters per second


class DownloaderFactory:
    """Factory class for creating appropriate book downloader instances."""

    _downloaders: Dict[str, Type[BaseBookDownloader]] = {}
    _domain_patterns: Dict[str, Type[BaseBookDownloader]] = {}
    _source_classes: Dict[str, Type[BaseBookDownloader]] = {}

    @classmethod
    def register(cls, domains: list[str], pattern: str = None):
        """
        Decorator to register a downloader class with its associated domains.

        Args:
            domains: List of domain names this downloader handles
            pattern: Optional regex pattern for more complex URL matching
        """

        def decorator(downloader_class: Type[BaseBookDownloader]):
            # Register by class name
            cls._source_classes[downloader_class.name] = downloader_class

            # Register by domains
            for domain in domains:
                cls._downloaders[domain] = downloader_class

            # Register by pattern
            if pattern:
                cls._domain_patterns[pattern] = downloader_class

            return downloader_class

        return decorator

    @classmethod
    def create_downloader(cls, url: str, output_dir: Path, start_chapter: Optional[int] = None,
                          end_chapter: Optional[int] = None) -> BaseBookDownloader:
        """
        Create appropriate downloader instance based on URL.

        Args:
            url: The book URL to download from
            output_dir: Directory to save downloaded content
            start_chapter: Chapter to start from
            end_chapter: Chapter to end at

        Returns:
            Instance of appropriate BaseBookDownloader subclass

        Raises:
            ValueError: If no suitable downloader is found for the URL
        """
        # Extract domain from URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()

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

        return downloader_class(output_dir, url, start_chapter, end_chapter)

    @classmethod
    def get_supported_domains(cls) -> list[str]:
        """
        Returns a list of domains that have been registered with the downloader factory.
        """
        return list(cls._downloaders.keys())

    @classmethod
    def get_source_info(cls) -> List[SourceInfo]:
        """
        Returns detailed information about all registered sources.

        Returns:
            List of SourceInfo objects with details about each source
        """
        source_infos = []

        # Group domains by downloader class
        domains_by_class = {}
        for domain, downloader_class in cls._downloaders.items():
            class_name = downloader_class.name
            if class_name not in domains_by_class:
                domains_by_class[class_name] = []
            domains_by_class[class_name].append(domain)

        # Create SourceInfo for each downloader class
        for name, downloader_class in cls._source_classes.items():
            # Calculate download speed (chapters per second)
            download_speed = cls._calculate_download_speed(downloader_class)

            source_infos.append(SourceInfo(
                name=name,
                domains=domains_by_class.get(name, []),
                bulk_download=downloader_class.bulk_download,
                concurrent_downloads=downloader_class.concurrent_downloads,
                request_delay=downloader_class.request_delay,
                source_language=downloader_class.source_language,
                download_speed=download_speed
            ))

        return source_infos

    @staticmethod
    def _calculate_download_speed(downloader_class: Type[BaseBookDownloader]) -> float:
        """
        Calculate download speed in chapters per second.

        Args:
            downloader_class: The downloader class to calculate for

        Returns:
            Download speed in chapters per second
        """
        # Assume 1 second per chapter as base download time
        base_time_per_chapter = 1.0
        overhead_factor = 0.1  # 10% overhead for parallel processing

        if downloader_class.bulk_download:
            # For bulk download, consider concurrent downloads
            concurrent = downloader_class.concurrent_downloads

            # Time for each batch: delay + (time per chapter + overhead)
            batch_time = downloader_class.request_delay + (base_time_per_chapter * (1 + overhead_factor))
            # Speed = chapters per batch / time per batch
            speed = concurrent / batch_time
        else:
            # For sequential download, speed is inverse of time per chapter
            time_per_chapter = base_time_per_chapter + downloader_class.request_delay
            speed = 1.0 / time_per_chapter

        return round(speed, 2)

    @classmethod
    def estimate_download_time(cls, source_name: str, chapter_count: int) -> float:
        """
        Estimate download time for a specific number of chapters from a source.

        Args:
            source_name: Name of the source
            chapter_count: Number of chapters to download

        Returns:
            Estimated time in seconds

        Raises:
            ValueError: If source name is not found
        """
        if source_name not in cls._source_classes:
            raise ValueError(f"Source '{source_name}' not found")

        downloader_class = cls._source_classes[source_name]
        speed = cls._calculate_download_speed(downloader_class)

        return chapter_count / speed
