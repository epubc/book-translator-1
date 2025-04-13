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
        return True

    lower_bound = start if start is not None else float('-inf')
    upper_bound = end if end is not None else float('inf')

    return lower_bound <= chapter_num <= upper_bound

def extract_chapter_number(filename: str) -> Optional[int]:
    """Extract chapter number from filename using regex."""
    match = re.search(r'\d+', filename)
    return int(match.group()) if match else None

