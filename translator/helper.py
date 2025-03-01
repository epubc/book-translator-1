import re
from typing import Optional



def is_in_chapter_range(
    filename: str,
    start: Optional[int],
    end: Optional[int]
) -> bool:
    """Check if file belongs to specified chapter range."""
    chapter_num = extract_chapter_number(filename)
    if chapter_num is None:
        return True  # Include files without chapter numbers

    lower_bound = start if start is not None else float('-inf')
    upper_bound = end if end is not None else float('inf')

    return lower_bound <= chapter_num <= upper_bound

def extract_chapter_number(filename: str) -> Optional[int]:
    """Extract chapter number from filename using regex."""
    match = re.search(r'\d+', filename)
    return int(match.group()) if match else None


def generate_chapter_suffix(start: Optional[int], end: Optional[int]) -> str:
    if start is None and end is None:
        return ""
    start_str = str(start) if start is not None else "begin"
    end_str = str(end) if end is not None else "end"
    return f"_{start_str}_{end_str}"


def sanitize_path_name(name: str) -> str:
    """Sanitize the directory name to remove invalid characters."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    # Truncate to avoid excessively long names
    max_length = 100
    return name.strip()[:max_length]
