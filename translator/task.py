import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class TranslationTask:
    """Dataclass to represent a translation task"""
    filename: str
    content: str


@dataclass
class FailedTranslationTask:
    """Dataclass to represent a failed translation task"""
    filename: str
    failure_description: str
    failure_type: str
    timestamp: float
    retried: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage in progress data"""
        return {
            "failure_description": self.failure_description,
            "failure_type": self.failure_type,
            "timestamp": self.timestamp,
            "retried": self.retried
        }

    @classmethod
    def from_dict(cls, filename: str, data: Dict) -> 'FailedTranslationTask':
        """Create a FailedTranslationTask from a dictionary"""
        return cls(
            filename=filename,
            failure_description=data.get("failure_description", ""),
            failure_type=data.get("failure_type", "generic"),
            timestamp=data.get("timestamp", time.time()),
            retried=data.get("retried", False)
        )
