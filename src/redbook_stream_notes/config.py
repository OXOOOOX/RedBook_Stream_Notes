from pathlib import Path
import os

from pydantic import BaseModel


class Settings(BaseModel):
    runtime_dir: Path = Path("runtime/jobs")
    framenotes_root: Path = Path(os.getenv("REDBOOK_FRAMENOTES_ROOT", "../FrameNotes"))
    default_chunk_seconds: int = 60
    sample_rate: int = 16000
    channels: int = 1

    @property
    def framenotes_transcribe_script(self) -> Path:
        return self.framenotes_root / "scripts" / "transcribe-audio.ps1"


settings = Settings()
