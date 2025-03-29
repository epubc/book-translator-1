from typing import Optional

from config import prompts
from config.prompts import PromptStyle


class PromptBuilder:
    """Handles building translation prompts"""

    @staticmethod
    def build_translation_prompt(
            text: str,
            additional_info: Optional[str],
            prompt_style: PromptStyle
    ) -> str:
        """Build prompt based on selected style."""
        base_prompt = {
            PromptStyle.Modern: prompts.MODERN_PROMPT,
            PromptStyle.ChinaFantasy: prompts.CHINA_FANTASY_PROMPT,
            PromptStyle.BookInfo: prompts.BOOK_INFO_PROMPT,
            PromptStyle.Sentences: prompts.SENTENCES_PROMPT,
            PromptStyle.IncompleteHandle: prompts.INCOMPLETE_HANDLE_PROMPT,
        }[PromptStyle(prompt_style)]
        text = f"[**NỘI DUNG ĐOẠN VĂN**]\n{text.strip()}\n[**NỘI DUNG ĐOẠN VĂN**]"
        if additional_info:
            return f"{base_prompt}\n{text}\n{base_prompt}\n\n{additional_info}".strip()
        return f"{base_prompt}\n{text}\n{base_prompt}".strip()
