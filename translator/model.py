import logging

from google.generativeai import GenerativeModel
import google.generativeai as genai

from config import settings
from config.models import ModelConfig, GEMINI_FLASH_LITE_MODEL_CONFIG, GEMINI_PRO_MODEL_CONFIG


class ModelManager:
    """Handles model initialization and selection"""

    def __init__(self, model_config: ModelConfig):
        self.primary_model = self._initialize_model(model_config)
        self.lite_model = self._initialize_model(GEMINI_FLASH_LITE_MODEL_CONFIG)
        self.pro_model = self._initialize_model(GEMINI_PRO_MODEL_CONFIG)
        self.primary_batch_size = model_config.BATCH_SIZE
        self.lite_batch_size = GEMINI_FLASH_LITE_MODEL_CONFIG.BATCH_SIZE
        self.pro_batch_size = GEMINI_PRO_MODEL_CONFIG.BATCH_SIZE

    def _initialize_model(self, model_config: ModelConfig) -> GenerativeModel:
        """Initialize a Gemini model with the given configuration."""
        if not model_config.MODEL_NAME:
            raise ValueError("Model name must be provided")
        genai.configure(api_key=settings.get_api_key())
        model = genai.GenerativeModel(
            model_name=model_config.MODEL_NAME,
            generation_config=model_config.GENERATION_CONFIG,
            safety_settings=model_config.SAFETY_SETTINGS
        )
        logging.info("Successfully initialized model: %s", model_config.MODEL_NAME)
        return model

    def select_model_for_task(self, is_retry: bool) -> GenerativeModel:
        """Select the appropriate model based on whether this is a retry or not."""
        return self.pro_model if is_retry else self.primary_model
