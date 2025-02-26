from pathlib import Path
from ebooklib import epub
from typing import Optional, List
import re

class EPUBGenerator:
    """Generates EPUB files from processed book content."""

    def create_epub_from_txt_files(
        self,
        txt_files: List[Path],
        title: str,
        author: str,
        output_filepath: Path,
        cover_image: Optional[str] = None,
        language: str = "en",
        identifier: Optional[str] = None,
        toc_title: str = "Table of Contents",
    ):
        """
        Creates an EPUB file from a list of text files.
        """
        if not txt_files:
            raise ValueError("At least one text file must be provided.")
        if not isinstance(txt_files, list):
            raise TypeError("txt_files argument must be a List.")
        for file_path in txt_files:
            if not file_path.exists():
                raise FileNotFoundError(f"Text file not found: {file_path}")

        book = epub.EpubBook()

        # Set metadata
        book.set_identifier(identifier or f"{title}-{author}")
        book.set_title(title)
        book.set_language(language)
        book.add_author(author)

        if cover_image:
            cover_path = Path(cover_image)
            if not cover_path.exists():
                raise FileNotFoundError(f"Cover image file not found: {cover_image}")
            book.set_cover("image.jpg", cover_path.read_bytes())

        chapters = []
        toc_entries = []
        for i, file_path in enumerate(txt_files):
            # Optional logging:
            # logger.debug(f"Processing file: {file_path}")
            with file_path.open("r", encoding="utf-8") as f:
                content = f.read()

            # --- Chapter Title Generation ---
            base_name = file_path.stem
            match = re.search(r'\d+$', base_name)
            if match:
                chapter_number = int(match.group(0))
                chapter_title = f"Chương {chapter_number}"
            else:
                chapter_title = base_name

            c = epub.EpubHtml(
                title=chapter_title, file_name=f"chapter_{i + 1}.xhtml", lang=language
            )

            # --- Content Formatting ---
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            html_content = f"<h1>{chapter_title}</h1>\n" + "".join(f"<p>{p}</p>" for p in paragraphs)
            c.content = html_content

            book.add_item(c)
            chapters.append(c)
            # Create a link for the Table of Contents
            toc_entries.append(epub.Link(f"chapter_{i + 1}.xhtml", chapter_title, f"chap{i+1}"))

        # --- Table of Contents ---
        book.toc = [(epub.Section(toc_title), tuple(toc_entries))]

        # --- Navigation Files ---
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # --- CSS Styling ---
        style = """
        @namespace epub "http://www.idpf.org/2007/ops";
        body {
            font-family: sans-serif;
        }
        h1 {
            text-align: center;
            font-weight: bold;
        }
        p {
            text-indent: 1.5em;
            margin-bottom: 0.5em;
        }
        """
        nav_css = epub.EpubItem(
            uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style
        )
        book.add_item(nav_css)

        book.spine = ["nav"] + chapters

        # Write the EPUB to file, converting the Path to a string
        epub.write_epub(str(output_filepath), book, {})
