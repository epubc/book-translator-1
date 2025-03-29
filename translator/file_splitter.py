

class FileSplitter:
    def __init__(self, file_path, output_dir):
        self.file_path = file_path
        self.output_dir = output_dir
        self.chapters_dir = self.output_dir / "input_chapters"
        self.chapters_dir.mkdir(exist_ok=True)

    def split_chapters(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        chapters = content.split('\n\n')
        for i, chapter in enumerate(chapters, 1):
            if chapter.strip():
                chapter_file = self.chapters_dir / f"chapter_{i:04d}.txt"
                with open(chapter_file, 'w', encoding='utf-8') as cf:
                    cf.write(chapter.strip())
