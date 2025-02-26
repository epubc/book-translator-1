from dataclasses import dataclass
from typing import Dict, Any
from google.generativeai.types import HarmCategory, HarmBlockThreshold


GENERATION_CONFIG = {
    "temperature": 0,
    "top_p": 0.95,
    "top_k": 64,
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


MODEL_CONFIGS = {
    "gemini-2.0-flash": ModelConfig("gemini-2.0-flash", 15, GENERATION_CONFIG, SAFETY_SETTINGS),
    "gemini-2.0-flash-lite": ModelConfig("gemini-2.0-flash-lite", 30, GENERATION_CONFIG, SAFETY_SETTINGS),
}

def get_model_config(model_name: str) -> ModelConfig:
    return MODEL_CONFIGS.get(model_name, ModelConfig("gemini-2.0-flash", 15, GENERATION_CONFIG, SAFETY_SETTINGS))
