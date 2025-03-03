from dataclasses import dataclass
from typing import Dict, Any
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from PyQt5.QtCore import QSettings


def get_generation_config() -> Dict[str, Any]:
    """Get generation config from settings or return defaults."""
    settings = QSettings("NovelTranslator", "Config")
    
    return {
        "temperature": settings.value("ModelTemperature", 0.0, type=float),
        "top_p": settings.value("ModelTopP", 0.95, type=float),
        "top_k": settings.value("ModelTopK", 64, type=int),
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }


SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


@dataclass
class ModelConfig:
    MODEL_NAME: str
    BATCH_SIZE: int
    GENERATION_CONFIG: Dict[str, Any]
    SAFETY_SETTINGS: Dict[HarmCategory, HarmBlockThreshold]

# Get the generation config dynamically
DEFAULT_GENERATION_CONFIG = get_generation_config()

DEFAULT_MODEL_CONFIG = ModelConfig("gemini-2.0-flash", 15, DEFAULT_GENERATION_CONFIG, SAFETY_SETTINGS)

MODEL_CONFIGS = {
    "gemini-2.0-flash": ModelConfig("gemini-2.0-flash", 15, DEFAULT_GENERATION_CONFIG, SAFETY_SETTINGS),
    "gemini-2.0-flash-lite": ModelConfig("gemini-2.0-flash-lite", 15, DEFAULT_GENERATION_CONFIG, SAFETY_SETTINGS),
}

def get_model_config(model_name: str) -> ModelConfig:
    """Get model configuration for the specified model with current settings."""
    generation_config = get_generation_config()
    
    model_configs = {
        "gemini-2.0-flash": ModelConfig(
            "gemini-2.0-flash", 15, generation_config, SAFETY_SETTINGS
        ),
        "gemini-2.0-flash-lite": ModelConfig(
            "gemini-2.0-flash-lite", 15, generation_config, SAFETY_SETTINGS
        ),
    }
    
    return model_configs.get(
        model_name, 
        ModelConfig("gemini-2.0-flash", 15, generation_config, SAFETY_SETTINGS)
    )
