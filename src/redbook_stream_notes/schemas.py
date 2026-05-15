from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


JobStatus = Literal["starting", "listening", "stopping", "stopped", "failed"]


class CreateJobRequest(BaseModel):
    url: HttpUrl
    chunk_seconds: int = Field(default=60, ge=15, le=600)
    language: str = "auto"
    asr_model: str = "small"
    asr_device: str = "auto"
    headless: bool = False
    max_chunks: int | None = Field(default=None, ge=1)


class TranscriptSegment(BaseModel):
    index: int
    start: float
    end: float
    start_text: str
    end_text: str
    text: str


class JobSnapshot(BaseModel):
    id: str
    url: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    chunks_completed: int
    note: str
    ended_reason: str | None = None
    error: str | None = None
    segments: list[TranscriptSegment] = []
