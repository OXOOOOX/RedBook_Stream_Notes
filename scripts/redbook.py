#!/usr/bin/env python3
"""Local service helper. Client commands use only the Python standard library."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"stopped", "failed"}


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def extract_url(text: str) -> str:
    """Extract one unambiguous Xiaohongshu URL without resolving it online."""
    urls = []
    for match in re.findall(r"https?://[^\s<>\"'，。！？；：、（）《》【】「」『』]+", text, flags=re.IGNORECASE):
        candidate = match.rstrip("，。！？；：、）》】」』,.;!?:)]}")
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower()
        if parsed.username or parsed.password:
            continue
        if any(host == domain or host.endswith("." + domain)
               for domain in ("xiaohongshu.com", "xhslink.com")):
            if candidate not in urls:
                urls.append(candidate)
    if len(urls) != 1:
        raise ValueError("Provide exactly one xiaohongshu.com or xhslink.com link in --url.")
    return urls[0]


def request_json(api: str, path: str, *, method: str = "GET",
                 payload: dict | None = None, timeout: float = 15) -> object:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(api.rstrip("/") + path, data=body, method=method,
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {api}: {exc.reason}. Start the local service first.") from exc


def compact(snapshot: dict) -> dict:
    fields = ("id", "status", "created_at", "updated_at", "chunks_completed", "ended_reason", "error")
    result = {key: snapshot.get(key) for key in fields}
    result["segment_count"] = len(snapshot.get("segments", []))
    return result


def doctor(check_audio: bool = False) -> int:
    """Inspect prerequisites; only --audio enumerates devices, never records."""
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    add("python", sys.version_info >= (3, 10), sys.version.split()[0])
    modules = ("fastapi", "uvicorn", "playwright", "soundcard", "soundfile", "numpy", "pydantic", "faster_whisper")
    for module in modules:
        present = importlib.util.find_spec(module) is not None
        add(module, present, "installed" if present else "missing: run python -m pip install -e .")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Asia/Shanghai")
        add("timezone", True, "Asia/Shanghai available")
    except Exception as exc:
        add("timezone", False, f"{exc}; install tzdata")
    if importlib.util.find_spec("playwright") is not None:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as browser_tool:
                executable = Path(browser_tool.chromium.executable_path)
            add("chromium", executable.is_file(), str(executable))
        except Exception as exc:
            add("chromium", False, str(exc))
    framenotes = Path(os.getenv("REDBOOK_FRAMENOTES_ROOT", str(ROOT.parent / "FrameNotes")))
    script = framenotes / "scripts" / "transcribe-audio.ps1"
    enabled = script.is_file() and bool(shutil.which("powershell"))
    add("framenotes", enabled, str(script) if enabled else "optional; faster-whisper will be used", required=False)
    if check_audio:
        try:
            import soundcard as sc
            speaker = sc.default_speaker()
            if speaker is None:
                raise RuntimeError("No default speaker")
            microphone = sc.get_microphone(id=str(speaker.name), include_loopback=True)
            if microphone is None:
                raise RuntimeError("No loopback input for default speaker")
            add("audio", True, f"speaker={speaker.name}; loopback={microphone.name}; capture not tested")
        except Exception as exc:
            add("audio", False, str(exc))
    ok = all(item["ok"] for item in checks if item["required"])
    emit({"ok": ok, "python": sys.executable, "skill_root": str(ROOT), "checks": checks,
          "scope": "No recording, model download, live-page access or ASR was performed."})
    return 0 if ok else 1


def serve(port: int, runtime_dir: str | None) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from redbook_stream_notes.config import settings
    import uvicorn

    # Resolve user-relative paths before changing CWD. Keep installed skill paths stable.
    destination = Path(runtime_dir).expanduser().resolve() if runtime_dir else ROOT / "runtime" / "jobs"
    destination.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir = destination
    os.chdir(ROOT)
    print(f"Viewer: http://127.0.0.1:{port}/viewer\nJob files: {destination}", flush=True)
    uvicorn.run("redbook_stream_notes.main:app", host="127.0.0.1", port=port, workers=1, reload=False)
    return 0


def export_snapshot(snapshot: dict, destination: Path) -> dict:
    """Create a new export directory; never replace an existing user's export."""
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    segments = snapshot.get("segments", [])
    rows = ["# 原始转写", "", f"- 任务：{snapshot['id']}", f"- 来源：{snapshot.get('url', '')}",
            f"- 状态：{snapshot.get('status', 'unknown')}", "",
            "时间戳为累计录音时间，不包含分段识别及预检间隔。", ""]
    rows.extend(f"- [{segment['start_text']} - {segment['end_text']}] {segment['text']}"
                for segment in segments)
    (destination / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "transcript.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (destination / "note.md").write_text(snapshot.get("note", ""), encoding="utf-8")
    return {"directory": str(destination), "files": ["snapshot.json", "transcript.md", "note.md"],
            "status": snapshot.get("status"), "segments": len(segments),
            "partial": snapshot.get("status") not in TERMINAL}


def bounded_int(low: int, high: int | None = None):
    def parse(value: str) -> int:
        number = int(value)
        if number < low or (high is not None and number > high):
            raise argparse.ArgumentTypeError(f"Expected {low}..{high or 'unbounded'}")
        return number
    return parse


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--api", default="http://127.0.0.1:8000", help="Service base URL; place before subcommand")
    commands = result.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="Check installed prerequisites without recording")
    check.add_argument("--audio", action="store_true", help="Also enumerate the default speaker and loopback")
    server = commands.add_parser("serve", help="Run a single local service in the foreground")
    server.add_argument("--port", type=bounded_int(1, 65535), default=8000)
    server.add_argument("--runtime-dir", help="Directory containing job folders (default: skill_root/runtime/jobs)")
    commands.add_parser("health", help="Check whether the service responds")
    commands.add_parser("recent", help="List compact snapshots of the latest 20 in-memory jobs")
    create = commands.add_parser("create", help="Open a live page and start recording system audio")
    create.add_argument("--url", required=True, help="One Xiaohongshu live URL or share text")
    create.add_argument("--chunk-seconds", type=bounded_int(15, 600), default=60)
    create.add_argument("--language", default="auto")
    create.add_argument("--model", default="small")
    create.add_argument("--device", default="auto")
    create.add_argument("--max-chunks", type=bounded_int(1))
    create.add_argument("--headless", action="store_true")
    for name, help_text in (("status", "Read a task snapshot"), ("stop", "Request graceful stop"),
                            ("export", "Export all currently available segments and rolling note")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("job_id")
        if name == "status":
            sub.add_argument("--compact", action="store_true")
        if name == "export":
            sub.add_argument("--output", required=True, type=Path, help="New directory; must not already exist")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor(args.audio)
        if args.command == "serve":
            return serve(args.port, args.runtime_dir)
        if args.command == "health":
            emit(request_json(args.api, "/health"))
        elif args.command == "recent":
            emit([compact(item) for item in request_json(args.api, "/jobs/recent")])
        elif args.command == "create":
            url = extract_url(args.url)
            active = [item for item in request_json(args.api, "/jobs/recent")
                      if item.get("status") not in TERMINAL]
            if active:
                raise RuntimeError("An active job already exists. Use recent/status or stop it before recording another stream.")
            payload = {"url": url, "chunk_seconds": args.chunk_seconds, "language": args.language,
                       "asr_model": args.model, "asr_device": args.device,
                       "headless": args.headless, "max_chunks": args.max_chunks}
            emit(request_json(args.api, "/jobs", method="POST", payload=payload))
        else:
            path = "/jobs/" + quote(args.job_id, safe="")
            snapshot = request_json(args.api, path)
            if args.command == "status":
                emit(compact(snapshot) if args.compact else snapshot)
            elif args.command == "stop":
                # Existing API rewrites terminal jobs to stopping. Avoid that mutation.
                if snapshot.get("status") not in TERMINAL | {"stopping"}:
                    snapshot = request_json(args.api, path + "/stop", method="POST")
                emit(snapshot)
            else:
                emit(export_snapshot(snapshot, args.output))
        return 0
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
