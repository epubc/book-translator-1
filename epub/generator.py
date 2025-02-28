from pathlib import Path
from ebooklib import epub
from typing import Optional, List, Dict
import re
import logging


class EPUBGenerator:
    """Generates EPUB files from processed book content with enhanced features and error handling."""

    def __init__(self, default_language: str = "en", default_css: Optional[str] = None):
        """
        Initialize the EPUBGenerator with default settings.

        Args:
            default_language: Default language code for the EPUB.
            default_css: Optional custom CSS to use for all generated EPUBs.
        """
        self.logger = logging.getLogger(__name__)
        self.default_language = default_language
        self.default_css = default_css or self._get_default_css()

    def _get_default_css(self) -> str:
        """Returns the default CSS styling for EPUBs."""
        return """
        @namespace epub "http://www.idpf.org/2007/ops";
        body {
            font-family: sans-serif;
            line-height: 1.5;
            margin: 1em;
        }
        h1 {
            text-align: center;
            font-weight: bold;
            margin-bottom: 1.5em;
            padding-bottom: 0.5em;
            border-bottom: 1px solid #eee;
        }
        p {
            text-indent: 1.5em;
            margin-bottom: 0.5em;
        }
        .no-indent {
            text-indent: 0;
        }
        """

    def _extract_chapter_title(self, file_path: Path, chapter_pattern: Optional[str] = None) -> str:
        """
        Extract chapter title from filename using pattern matching.

        Args:
            file_path: Path to the chapter file
            chapter_pattern: Optional regex pattern to extract chapter number

        Returns:
            Formatted chapter title
        """
        base_name = file_path.stem

        # Use provided pattern or default to looking for digits at the end
        pattern = chapter_pattern or r'\d+$'
        match = re.search(pattern, base_name)

        if match:
            chapter_number = int(match.group(0))
            return f"Chương {chapter_number}"
        else:
            # If no pattern match, use the filename as title with first letter capitalized
            return ' '.join(word.capitalize() for word in base_name.replace('_', ' ').split())

    def _format_chapter_content(self, raw_content: str, chapter_title: str) -> str:
        """
        Format chapter content into HTML with proper paragraph structure.

        Args:
            raw_content: Raw text content from file
            chapter_title: Title for the chapter

        Returns:
            Formatted HTML content
        """
        # Split content into paragraphs, preserving empty lines as scene breaks
        paragraphs = []
        for p in raw_content.split("\n\n"):
            p = p.strip()
            if not p:
                # Add a scene break with proper styling
                paragraphs.append('<div class="scene-break">* * *</div>')
            else:
                paragraphs.append(f"<p>{p}</p>")

        # Create HTML with title and paragraphs
        html_content = f"<h1>{chapter_title}</h1>\n" + "\n".join(paragraphs)
        return html_content

    def create_epub_from_txt_files(
            self,
            txt_files: List[Path],
            title: str,
            author: str,
            output_filepath: Path,
            cover_image: Optional[str] = None,
            language: Optional[str] = None,
            identifier: Optional[str] = None,
            toc_title: str = "Table of Contents",
            chapter_pattern: Optional[str] = None,
            custom_css: Optional[str] = None,
            metadata: Optional[Dict[str, str]] = None
    ):
        """
        Creates an EPUB file from a list of text files with enhanced features.

        Args:
            txt_files: List of paths to text files
            title: Book title
            author: Book author
            output_filepath: Path for output EPUB file
            cover_image: Optional path to cover image
            language: Language code (defaults to instance default)
            identifier: Book identifier (defaults to title-author)
            toc_title: Title for table of contents
            chapter_pattern: Optional regex pattern to extract chapter numbers
            custom_css: Optional CSS to override default styling
            metadata: Optional additional metadata as key-value pairs

        Raises:
            ValueError: If no text files provided
            TypeError: If txt_files is not a list
            FileNotFoundError: If text file or cover image not found
        """
        # Input validation
        if not txt_files:
            raise ValueError("At least one text file must be provided.")
        if not isinstance(txt_files, list):
            raise TypeError("txt_files argument must be a List of Path objects.")

        # Verify all files exist
        missing_files = [file_path for file_path in txt_files if not file_path.exists()]
        if missing_files:
            raise FileNotFoundError(f"Text files not found: {', '.join(str(f) for f in missing_files)}")

        # Create new EPUB book
        self.logger.info(f"Creating EPUB: {title} by {author}")
        book = epub.EpubBook()

        # Set metadata
        book.set_identifier(identifier or f"{title}-{author}".replace(" ", "-"))
        book.set_title(title)
        book.set_language(language or self.default_language)
        book.add_author(author)

        # Add additional metadata if provided
        if metadata:
            for key, value in metadata.items():
                book.add_metadata('DC', key, value)

        # Add cover if provided
        if cover_image:
            cover_path = Path(cover_image)
            if not cover_path.exists():
                raise FileNotFoundError(f"Cover image file not found: {cover_image}")
            self.logger.info(f"Adding cover image: {cover_image}")
            book.set_cover("cover.jpg", open(cover_path, 'rb').read())

        # Process chapters
        chapters = []
        toc_entries = []

        # Sort files if they have numerical names to ensure proper order
        if all(re.search(r'\d+', file.stem) for file in txt_files):
            txt_files.sort(key=lambda x: int(re.search(r'\d+', x.stem).group()))

        for i, file_path in enumerate(txt_files):
            self.logger.debug(f"Processing file {i + 1}/{len(txt_files)}: {file_path}")

            try:
                with file_path.open("r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                self.logger.warning(f"UTF-8 decode error, trying with alternate encoding: {file_path}")
                with file_path.open("r", encoding="latin-1") as f:
                    content = f.read()

            # Extract chapter title
            chapter_title = self._extract_chapter_title(file_path, chapter_pattern)

            # Create chapter
            chapter_filename = f"chapter_{i + 1:03d}.xhtml"
            c = epub.EpubHtml(
                title=chapter_title,
                file_name=chapter_filename,
                lang=language or self.default_language
            )

            # Format content
            c.content = self._format_chapter_content(content, chapter_title)

            # Add chapter to book
            book.add_item(c)
            chapters.append(c)

            # Create TOC entry
            toc_entries.append(
                epub.Link(chapter_filename, chapter_title, f"chap{i + 1}")
            )

        # Create table of contents
        book.toc = [(epub.Section(toc_title), tuple(toc_entries))]

        # Add required navigation files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Add CSS styling
        css_content = custom_css or self.default_css
        nav_css = epub.EpubItem(
            uid="style_nav",
            file_name="style/nav.css",
            media_type="text/css",
            content=css_content
        )
        book.add_item(nav_css)

        # Define the spine (reading order)
        book.spine = ["nav"] + chapters

        # Ensure output directory exists
        output_filepath.parent.mkdir(parents=True, exist_ok=True)

        # Write the EPUB to file
        self.logger.info(f"Writing EPUB to: {output_filepath}")
        epub.write_epub(str(output_filepath), book, {})

        return output_filepath