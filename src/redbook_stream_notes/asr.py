from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from .config import settings
from .schemas import TranscriptSegment


def fmt_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d}.{millis:03d}"


class Transcriber:
    def __init__(self, model: str, language: str = "auto", device: str = "auto") -> None:
        self.model = model
        self.language = language
        self.device = device
        self._fallback_model = None

    async def transcribe(self, audio_path: Path, output_dir: Path, offset_seconds: float) -> list[TranscriptSegment]:
        audio_path = audio_path.resolve()
        output_dir = output_dir.resolve()
        if settings.framenotes_transcribe_script.exists() and shutil.which("powershell"):
            return await self._transcribe_with_framenotes(audio_path, output_dir, offset_seconds)
        return await asyncio.to_thread(self._transcribe_with_faster_whisper, audio_path, output_dir, offset_seconds)

    async def _transcribe_with_framenotes(
        self,
        audio_path: Path,
        output_dir: Path,
        offset_seconds: float,
    ) -> list[TranscriptSegment]:
        process = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(settings.framenotes_transcribe_script),
            str(audio_path),
            "-Model",
            self.model,
            "-Language",
            self.language,
            "-Device",
            self.device,
            cwd=str(output_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace"))
        transcript_json = audio_path.parent / "transcript.json"
        return load_segments(transcript_json, offset_seconds)

    def _transcribe_with_faster_whisper(
        self,
        audio_path: Path,
        output_dir: Path,
        offset_seconds: float,
    ) -> list[TranscriptSegment]:
        from faster_whisper import WhisperModel

        if self._fallback_model is None:
            device = "cpu" if self.device == "auto" else self.device
            self._fallback_model = WhisperModel(self.model, device=device, compute_type="int8")

        options = {"vad_filter": True, "beam_size": 5}
        if self.language != "auto":
            options["language"] = self.language
        segments, _ = self._fallback_model.transcribe(str(audio_path), **options)

        rows = []
        for index, segment in enumerate(segments, start=1):
            start = offset_seconds + float(segment.start)
            end = offset_seconds + float(segment.end)
            rows.append(
                TranscriptSegment(
                    index=index,
                    start=start,
                    end=end,
                    start_text=fmt_time(start),
                    end_text=fmt_time(end),
                    text=segment.text.strip(),
                )
            )
        payload = {"audio": str(audio_path), "segments": [row.model_dump() for row in rows]}
        (output_dir / "transcript.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return rows


def load_segments(path: Path, offset_seconds: float) -> list[TranscriptSegment]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for item in data.get("segments", []):
        start = offset_seconds + float(item["start"])
        end = offset_seconds + float(item["end"])
        rows.append(
            TranscriptSegment(
                index=int(item["index"]),
                start=start,
                end=end,
                start_text=fmt_time(start),
                end_text=fmt_time(end),
                text=str(item["text"]).strip(),
            )
        )
    return rows
