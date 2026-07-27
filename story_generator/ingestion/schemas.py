from typing import Any, Literal

from pydantic import BaseModel
from datetime import datetime


class SyncRunResponse(BaseModel):
    id: int
    source: str
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    summary: dict[str, Any]


class SyncStatusResponse(BaseModel):
    latest_run: SyncRunResponse | None