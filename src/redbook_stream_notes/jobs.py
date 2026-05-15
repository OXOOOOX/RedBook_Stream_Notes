from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from .asr import Transcriber
from .browser import BrowserSession, inspect_live_state, open_live_page
from .config import settings
from .notes import build_note, build_refined_note
from .recorder import LoopbackRecorder
from .schemas import CreateJobRequest, JobSnapshot, JobStatus, TranscriptSegment


@dataclass
class StreamJob:
    id: str
    request: CreateJobRequest
    directory: Path
    status: JobStatus = "starting"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    chunks_completed: int = 0
    note: str = "# 直播笔记\n\n等待开始。"
    ended_reason: str | None = None
    error: str | None = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None

    def snapshot(self) -> JobSnapshot:
        return JobSnapshot(
            id=self.id,
            url=str(self.request.url),
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            chunks_completed=self.chunks_completed,
            note=self.note,
            ended_reason=self.ended_reason,
            error=self.error,
            segments=self.segments,
        )

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, StreamJob] = {}
        self.recorder = LoopbackRecorder(settings.sample_rate, settings.channels)

    def create(self, request: CreateJobRequest) -> StreamJob:
        job_id = uuid4().hex[:12]
        directory = settings.runtime_dir / job_id
        directory.mkdir(parents=True, exist_ok=True)
        job = StreamJob(id=job_id, request=request, directory=directory)
        self.jobs[job_id] = job
        job.task = asyncio.create_task(self._run(job))
        return job

    def get(self, job_id: str) -> StreamJob | None:
        return self.jobs.get(job_id)

    async def stop(self, job_id: str) -> StreamJob | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        job.status = "stopping"
        job.stop_event.set()
        job.touch()
        if job.task:
            await asyncio.wait([job.task], timeout=5)
        return job

    async def _run(self, job: StreamJob) -> None:
        browser: BrowserSession | None = None
        try:
            transcriber = Transcriber(job.request.asr_model, job.request.language, job.request.asr_device)
            browser = await open_live_page(str(job.request.url), headless=job.request.headless)
            job.status = "listening"
            job.note = "# 直播笔记\n\n浏览器已打开，等待直播音频。"
            job.touch()

            while not job.stop_event.is_set():
                if job.request.max_chunks and job.chunks_completed >= job.request.max_chunks:
                    job.ended_reason = "max_chunks_reached"
                    break

                state = await inspect_live_state(browser.page)
                if state.get("ended"):
                    job.ended_reason = str(state.get("reason") or "live_ended")
                    job.note = finish_note(job, "检测到直播结束，已停止监听。")
                    (job.directory / "note.md").write_text(job.note, encoding="utf-8")
                    write_refined_note(job)
                    job.touch()
                    break

                chunk_index = job.chunks_completed + 1
                chunk_dir = job.directory / f"chunk_{chunk_index:04d}"
                audio_path = chunk_dir / "audio.wav"
                await asyncio.to_thread(self.recorder.record_chunk, audio_path, job.request.chunk_seconds)

                state = await inspect_live_state(browser.page)
                if state.get("ended"):
                    job.ended_reason = str(state.get("reason") or "live_ended")

                stats = await asyncio.to_thread(inspect_audio, audio_path)
                if stats["peak"] < 0.001:
                    job.chunks_completed += 1
                    job.note = (
                        "# 直播笔记\n\n"
                        "当前分段录到静音，尚无可转写内容。请确认网页直播正在播放、系统默认扬声器有声音，"
                        "并且没有同时使用耳机或虚拟声卡导致 loopback 录错设备。\n"
                    )
                    (job.directory / "note.md").write_text(job.note, encoding="utf-8")
                    job.touch()
                    if job.ended_reason:
                        break
                    continue

                offset = job.chunks_completed * job.request.chunk_seconds
                new_segments = await transcriber.transcribe(audio_path, chunk_dir, offset)
                for segment in new_segments:
                    segment.index = len(job.segments) + 1
                    job.segments.append(segment)

                job.chunks_completed += 1
                job.note = build_note(job.segments, str(job.request.url))
                if job.ended_reason:
                    job.note = job.note.rstrip() + f"\n\n## 监听状态\n\n检测到直播结束：{job.ended_reason}\n"
                (job.directory / "note.md").write_text(job.note, encoding="utf-8")
                if job.ended_reason:
                    write_refined_note(job)
                job.touch()
                if job.ended_reason:
                    break

            job.status = "stopped"
            write_refined_note(job)
            job.touch()
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.touch()
        finally:
            if browser is not None:
                await browser.close()


manager = JobManager()


def inspect_audio(audio_path: Path) -> dict[str, float]:
    audio, sample_rate = sf.read(audio_path, always_2d=True)
    if audio.size == 0:
        return {"sample_rate": float(sample_rate), "duration": 0.0, "rms": 0.0, "peak": 0.0}
    rms = float(np.sqrt(np.mean(audio * audio)))
    peak = float(np.max(np.abs(audio)))
    return {
        "sample_rate": float(sample_rate),
        "duration": float(len(audio) / sample_rate),
        "rms": rms,
        "peak": peak,
    }


def finish_note(job: StreamJob, message: str) -> str:
    note = build_note(job.segments, str(job.request.url)) if job.segments else "# 直播笔记\n\n暂无可转写内容。"
    return note.rstrip() + f"\n\n## 监听状态\n\n{message}\n"


def write_refined_note(job: StreamJob) -> None:
    if not job.segments:
        return
    refined = build_refined_note(job.segments, str(job.request.url), job.ended_reason)
    (job.directory / "refined_note.md").write_text(refined, encoding="utf-8")
