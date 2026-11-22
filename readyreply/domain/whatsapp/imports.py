"""One automatic import of a chat file, as shown in the history."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ImportedChat:
    imported_at: datetime
    answers: int
    questions: int
    details: int
    error: str | None = None
    """Error code when the file could not be imported (it is not retried)."""
