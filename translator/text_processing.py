import re

import jieba
from typing import List, Tuple
import string
from deep_translator import GoogleTranslator

REPLACEMENTS = {
    "chị rể": "anh rể"
}

def preprocess_downloaded_text(text: str) -> str:
    """Normalizes line spacing in a chapter file."""
    text = re.sub(r'<[^>]+>', '', text)
    lines = text.splitlines()
    normalized_lines = []
    for line in lines:
        if "https://" in line:
            continue  # Skip empty lines
        normalized_lines.append(line)

    return "\n".join(normalized_lines)


def detect_untranslated_chinese(text: str) -> Tuple[bool, float]:
    """Detects Chinese characters, returns if present and ratio."""
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    total_chars = len(text)
    ratio = (len(chinese_chars) / total_chars) * 100 if total_chars > 0 else 0
    return (len(chinese_chars) > 0), ratio


def extract_potential_names(words: List[str]) -> List[List[str]]:
    """Extract sequences of potential name parts (capitalized words)."""
    potential_names: List[List[str]] = []
    current_name: List[str] = []
    for word in words:
        if is_potential_name_part(word):
            current_name.append(word)
        else:
            if current_name:
                potential_names.append(current_name)
                current_name = []
    if current_name:
        potential_names.append(current_name)
    return potential_names


def is_potential_name_part(word: str) -> bool:
    """Check if a word could be part of a name (Capitalized, alphabetic)."""
    return word[0].isalpha() and word[0].isupper() if word else False


def clean_name_string(name_joined: str) -> str:
    """Remove punctuation and special chars from name strings for consistency."""
    allowed_punct = "-'"
    punct_to_remove = ''.join([p for p in string.punctuation if p not in allowed_punct])
    return name_joined.translate(str.maketrans('', '', punct_to_remove)).strip()


def is_valid_name(name: List[str]) -> bool:
    """Validate name length and basic punctuation rules."""
    if not (2 <= len(name) <= 4):
        return False
    name_joined = "".join(name)
    cleaned_name = clean_name_string(name_joined)
    if cleaned_name != name_joined.translate(str.maketrans('', '', string.punctuation)):
        return False
    return True


def get_unique_names_from_text(text: str) -> dict[str, int]:
    """Extract unique names, count occurrences, return dict."""
    name_counts: dict[str, int] = {}
    words = text.split()
    potential_names_list = extract_potential_names(words)

    for name_parts in potential_names_list:
        if is_valid_name(name_parts):
            cleaned_name = clean_name_string(" ".join(name_parts))
            name_counts[cleaned_name] = name_counts.get(cleaned_name, 0) + 1
    return name_counts



def split_text_into_chunks(text: str, chunk_size: int) -> List[str]:
    """Split text into chunks of max chunk_size, trying to respect line breaks."""
    chunks: List[str] = []
    current_chunk = ""

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if len(line) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = ""
            for i in range(0, len(line), chunk_size):
                chunks.append(line[i:i + chunk_size])
            continue

        separator = "\n" if current_chunk else ""
        if len(current_chunk) + len(separator) + len(line) <= chunk_size:
            current_chunk += separator + line
        else:
            chunks.append(current_chunk)
            current_chunk = line

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def clean_filename(filename: str) -> str:
    """Remove all suffixes after chapter and index numbers.

    Examples:
        chapter_1_1_translated.txt -> chapter_1_1
        chapter_2_2_xxx.txt -> chapter_2_2
    """
    # Match the pattern chapter_number_number and ignore everything after
    match = re.match(r'(chapter_\d+_\d+).*', filename)
    if match:
        return match.group(1)
    return filename.split('_')[0]


def normalize_translation(translation_content: str) -> str:
    """Normalizes line spacing and applies replacements in a chapter file."""
    lines = translation_content.splitlines()
    normalized_lines = []

    for line in lines:
        stripped_line = line.strip()
        if not stripped_line:
            continue  # Skip empty lines
        if all(c == '*' for c in stripped_line):
            normalized_lines.append(stripped_line)
            continue

        # Normalize spaces and underscores
        processed_line = stripped_line.replace('_', ' ')
        processed_line = re.sub(r'\s{2,}', ' ', processed_line)
        processed_line = processed_line.replace('**', '')

        # Apply each replacement rule
        for pattern, replacement in REPLACEMENTS.items():
            regex = re.compile(re.escape(pattern), flags=re.IGNORECASE)
            processed_line = regex.sub(
                lambda match: replacement[0].upper() + replacement[1:]
                if match.group()[0].isupper()
                else replacement,
                processed_line
            )

        normalized_lines.append(processed_line)

    return "\n\n".join(normalized_lines)

def tokenize_chinese_text(text):
    """
    Tokenizes Chinese text using the jieba library.

    Args:
        text: The Chinese text string to be tokenized.

    Returns:
        A list of tokens (words).  Returns an empty list if input is invalid.
    """
    if not isinstance(text, str):
        print("Error: Input must be a string.")
        return []  # Or raise a TypeError, depending on your needs

    seg_list = jieba.cut(text)  # Use jieba.cut for tokenization
    return list(seg_list)  # Convert the generator to a list


def add_underscore(text, is_chinese=True):
    if detect_underscore(text):
        return text
    lines = text.splitlines()
    normalized_lines = []
    for line in lines:
        line = line.strip()
        if is_chinese:
            normalized_lines.append('_'.join(tokenize_chinese_text(line)))
        else:
            normalized_lines.append('_'.join(line.split(" ")))
    return "\n".join(normalized_lines)


def detect_underscore(text):
    lines = text.splitlines()
    underscore_pattern = re.compile(r'_\w+_')

    for line in lines:
        if underscore_pattern.search(line):
            return True

    return False

def remove_underscore(text: str) -> str:
    """Normalizes line spacing in a chapter file."""
    lines = text.splitlines()
    normalized_lines = []
    for line in lines:
        line = line.replace('_', '')
        normalized_lines.append(line)

    return "\n".join(normalized_lines)



def validate_translation_quality(text: str, retry_count: int) -> None:
    """Validate translated text contains minimal Chinese characters."""
    has_chinese, ratio = detect_untranslated_chinese(text)
    if has_chinese and (ratio > 0.05 or retry_count < 3):
        raise ValueError(f"Excessive Chinese characters ({ratio:.2f}%)")


def translate_long_text(text: str, src: str, dest: str, chunk_size: int = 1024) -> str:
    """
    Splits the input text into chunks, translates each chunk synchronously,
    and then combines the translations.
    """
    chunks = split_text_into_chunks(text, chunk_size)
    translator = GoogleTranslator(source=src, target=dest)
    translated_chunks = []
    for chunk in chunks:
        translated = translator.translate(chunk)
        translated_chunks.append(translated)
    return "\n".join(translated_chunks)


def preprocess_raw_text(text: str, retry_count: int) -> str:
    if retry_count < 5:
        return text
    text = remove_underscore(text)
    text = translate_long_text(text, src="zh", dest="en", chunk_size=1024)
    return add_underscore(text)
