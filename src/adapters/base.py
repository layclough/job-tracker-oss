from abc import ABC, abstractmethod
from typing import NamedTuple


class ExtractedJob(NamedTuple):
    title: str
    body_text: str
    salary: str | None = None
    source_type: str = "api"  # "api" or "browser"


class BaseATSAdapter(ABC):
    """Abstract Base Class for all Applicant Tracking System (ATS) direct API adapters."""

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Determines whether the given URL matches this specific ATS platform."""
        pass

    @abstractmethod
    def extract(self, url: str) -> ExtractedJob | None:
        """Fetches from direct public JSON endpoint and returns structured job data.
        
        Returns None or raises an Exception if the URL cannot be fetched directly.
        """
        pass
