import logging
import re
from pathlib import Path
from typing import Dict, Optional, Callable

from text_processing.text_processing import split_text_into_chunks, add_underscore
from translator.helper import is_in_chapter_range
from config import settings


def is_translation_complete(
        prompts_dir: Path,
        responses_dir: Path,
        progress_data: Dict,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
) -> bool:
    """Check if all expected translations in specified chapter range are completed."""
    # Generate display strings for logging
    start_str = str(start_chapter) if start_chapter is not None else 'begin'
    end_str = str(end_chapter) if end_chapter is not None else 'end'

    # Get filtered prompts and responses
    prompt_files = {
        p.stem for p in prompts_dir.glob("*.txt")
        if is_in_chapter_range(p.name, start_chapter, end_chapter)
    }

    response_files = {
        r.stem
        for r in responses_dir.glob("*.txt")
        if is_in_chapter_range(r.name, start_chapter, end_chapter)
    }

    # Get failed translations from progress data
    failed_translations = progress_data.get("failed_translations", {})

    untranslated_prompts = set()
    for prompt_file in prompt_files:
        if prompt_file not in response_files:
            untranslated_prompts.add(prompt_file)
        else:
            failure_info = failed_translations.get(f"{prompt_file}.txt")
            if failure_info and not failure_info.get("retried", False):
                untranslated_prompts.add(prompt_file)

    if untranslated_prompts:
        logging.info(f"Remaining translations in chapters {start_str}-{end_str}: {len(untranslated_prompts)}")
        return False

    logging.info(f"All translations completed for chapters {start_str}-{end_str}")
    return True


def combine_translations(
        translated_responses_dir: Path,
        translated_chapters_dir: Path,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
) -> None:
    """Combines translated prompt files for each chapter."""
    response_files = [
        p for p in translated_responses_dir.glob("*.txt")
        if is_in_chapter_range(p.name, start_chapter, end_chapter)
    ]

    chapter_files = {}
    for filename in response_files:
        match = re.match(r"(.*)_\d+\.txt", filename.name)
        if match:
            chapter_name = match.group(1)
            if chapter_name not in chapter_files:
                chapter_files[chapter_name] = []
            chapter_files[chapter_name].append(filename)

    # Combine files for each chapter
    for chapter_name in sorted(chapter_files.keys()):
        # Optionally, sort the files for each chapter
        files = sorted(chapter_files[chapter_name])

        output_path = translated_chapters_dir / f"{chapter_name}.txt"
        try:
            with open(output_path, "w", encoding="utf-8") as outfile:
                for file_path in files:
                    try:
                        with open(file_path, "r", encoding="utf-8") as infile:
                            content = infile.read()
                            outfile.write(content + "\n")  # Add newline between prompts
                    except Exception as e:
                        logging.error(f"Error reading file {file_path}: {e}")
                logging.info(f"Combined chapter translation: {chapter_name}")
        except OSError as e:
            logging.error(f"Error writing to {output_path}: {e}")

    logging.info("Combine chapter translations complete")


def create_prompt_files(
        download_dir: Path,
        prompt_dir: Path,
        load_content_from_file: Callable,
        save_content_to_file: Callable,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
) -> None:
    """Create prompt files from downloaded chapters, but only for chapters without existing prompt files."""
    prompt_count = 0
    new_chapter_count = 0

    chapter_files = [
        p for p in download_dir.glob("*.txt")
        if is_in_chapter_range(p.name, start_chapter, end_chapter)
    ]
    if not chapter_files:
        logging.warning(f"No chapter files found in: {download_dir}")
        return

    # Get existing prompt file prefixes (chapter names)
    existing_prompts = set()
    for prompt_file in prompt_dir.glob("*.txt"):
        # Extract chapter name from prompt filename (e.g., "chapter_0001_1.txt" -> "chapter_0001")
        match = re.match(r"(.*)_\d+\.txt", prompt_file.name)
        if match:
            existing_prompts.add(match.group(1))

    for chapter_file in chapter_files:
        # Skip if this chapter already has prompt files
        if chapter_file.stem in existing_prompts:
            logging.debug(f"Skipping {chapter_file.stem} - prompt files already exist")
            continue

        chapter_text = load_content_from_file(chapter_file.name, "input_chapters")
        if chapter_text:
            new_chapter_count += 1
            prompts = split_text_into_chunks(chapter_text, settings.MAX_TOKENS_PER_PROMPT)
            for idx, prompt_text in enumerate(prompts):
                prompt_filename = f"{chapter_file.stem}_{idx + 1}.txt"
                save_content_to_file(add_underscore(prompt_text), prompt_filename, "prompt_files")
                prompt_count += 1

    if new_chapter_count > 0:
        logging.info(f"Created {prompt_count} prompt files from {new_chapter_count} new chapters.")
    else:
        logging.info("No new chapters to process - all chapters already have prompt files.")


def get_chapters_status(
        prompts_dir: Path,
        responses_dir: Path,
        load_progress: Callable,
        load_content_from_file: Callable,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
) -> Dict[str, Dict[str, any]]:
    """Get status information for all chapters in the specified range."""
    # Ensure directories exist
    prompts_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)

    # Get all prompt files in the specified range
    prompt_files = [
        p for p in prompts_dir.glob("*.txt")
        if is_in_chapter_range(p.name, start_chapter, end_chapter)
    ]

    # Get all response files in the specified range
    response_files = [
        r for r in responses_dir.glob("*.txt")
        if is_in_chapter_range(r.name, start_chapter, end_chapter)
    ]

    # Group prompt files by chapter
    chapter_status = {}
    for file_path in prompt_files:
        match = re.match(r"(.*)_\d+\.txt", file_path.name)
        if match:
            chapter_name = match.group(1)
            if chapter_name not in chapter_status:
                chapter_status[chapter_name] = {
                    "total_shards": 0,
                    "translated_shards": 0,
                    "failed_shards": 0,
                    "status": "Not Started",
                    "progress": 0.0,
                    "failed": False
                }
            chapter_status[chapter_name]["total_shards"] += 1

    # First check progress.json for failed translations
    progress_data = load_progress()
    if "failed_translations" in progress_data:
        for filename, failure_info in progress_data["failed_translations"].items():
            match = re.match(r"(.*)_\d+\.txt", filename)
            if match:
                chapter_name = match.group(1)
                if chapter_name in chapter_status:
                    # Count as failed shard
                    chapter_status[chapter_name]["failed_shards"] += 1
                    chapter_status[chapter_name]["failed"] = True
                    # Store failure details
                    chapter_status[chapter_name]["failure_type"] = failure_info.get("failure_type", "generic")
                    chapter_status[chapter_name]["error"] = failure_info.get("error", "Unknown error")

    # Then count translated and failed shards from files
    for file_path in response_files:
        match = re.match(r"(.*)_\d+\.txt", file_path.name)
        if match:
            chapter_name = match.group(1)
            if chapter_name in chapter_status:
                content = load_content_from_file(file_path.name, "translation_responses")
                if content:
                    if "[TRANSLATION FAILED]" in content:
                        # Only count as failed if not already counted from progress.json
                        if not any(filename == file_path.name for filename in
                                   progress_data.get("failed_translations", {})):
                            chapter_status[chapter_name]["failed_shards"] += 1
                            chapter_status[chapter_name]["failed"] = True
                    else:
                        # Only count as translated if not marked as failed in progress.json
                        if not any(filename == file_path.name for filename in
                                   progress_data.get("failed_translations", {})):
                            chapter_status[chapter_name]["translated_shards"] += 1

    # Calculate progress and set status for each chapter
    for chapter_name, status in chapter_status.items():
        if status["total_shards"] > 0:
            # Calculate progress based on successful translations only
            total_processed = status["translated_shards"]
            status["progress"] = round((total_processed / status["total_shards"]) * 100, 1)

            # Set chapter status
            if status["failed"]:
                # Any chapter with failed shards is marked as Incomplete
                status["status"] = "Incomplete"
            elif status["translated_shards"] == status["total_shards"]:
                status["status"] = "Translated"
            elif status["translated_shards"] > 0:
                status["status"] = "Translating"

    # Sort chapters for better readability in logs
    return dict(sorted(chapter_status.items()))
