import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from .jobs import manager
from .schemas import CreateJobRequest, JobSnapshot


app = FastAPI(title="RedBook Stream Notes", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/viewer", response_class=HTMLResponse)
async def viewer() -> str:
    return VIEWER_HTML


@app.get("/jobs/recent", response_model=list[JobSnapshot])
async def recent_jobs() -> list[JobSnapshot]:
    jobs = sorted(manager.jobs.values(), key=lambda item: item.created_at, reverse=True)
    return [job.snapshot() for job in jobs[:20]]


@app.post("/jobs", response_model=JobSnapshot)
async def create_job(request: CreateJobRequest) -> JobSnapshot:
    job = manager.create(request)
    return job.snapshot()


@app.get("/jobs/{job_id}", response_model=JobSnapshot)
async def get_job(job_id: str) -> JobSnapshot:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.snapshot()


@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def stream():
        last_signature = None
        while True:
            job = manager.get(job_id)
            if job is None:
                payload = {"status": "missing", "error": "job not found"}
                yield sse("job", payload)
                break
            snapshot = job.snapshot().model_dump(mode="json")
            signature = (
                snapshot["status"],
                snapshot["chunks_completed"],
                len(snapshot["segments"]),
                snapshot["updated_at"],
                snapshot.get("ended_reason"),
                snapshot.get("error"),
            )
            if signature != last_signature:
                last_signature = signature
                yield sse("job", snapshot)
            if snapshot["status"] in {"stopped", "failed"}:
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/jobs/{job_id}/stop", response_model=JobSnapshot)
async def stop_job(job_id: str) -> JobSnapshot:
    job = await manager.stop(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.snapshot()


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


VIEWER_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小红书直播转写</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f6f7f8; color: #1f2933; }
    header { height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 20px; background: #fff; border-bottom: 1px solid #e5e7eb; position: sticky; top: 0; z-index: 2; }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    main { display: grid; grid-template-columns: 360px 1fr; gap: 16px; padding: 16px; }
    section { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; min-width: 0; }
    .panel { padding: 14px; }
    label { display: block; font-size: 13px; color: #52606d; margin-bottom: 6px; }
    input, textarea, button { font: inherit; }
    input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #cbd2d9; border-radius: 6px; padding: 9px 10px; background: #fff; color: #1f2933; }
    textarea { min-height: 90px; resize: vertical; }
    button { border: 0; border-radius: 6px; background: #2563eb; color: #fff; padding: 9px 12px; cursor: pointer; }
    button.secondary { background: #4b5563; }
    button.danger { background: #dc2626; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .row { display: flex; gap: 8px; margin-top: 10px; }
    .row > * { flex: 1; }
    .status { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
    .metric { background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px; padding: 9px; }
    .metric b { display: block; font-size: 12px; color: #6b7280; margin-bottom: 3px; }
    .metric span { font-size: 14px; overflow-wrap: anywhere; }
    .tabs { display: flex; gap: 6px; border-bottom: 1px solid #e5e7eb; padding: 8px 8px 0; }
    .tab { background: transparent; color: #374151; border: 1px solid transparent; border-bottom: 0; padding: 8px 10px; }
    .tab.active { background: #fff; border-color: #e5e7eb; color: #111827; }
    .content { height: calc(100vh - 130px); overflow: auto; padding: 16px; }
    .segments { display: flex; flex-direction: column; gap: 8px; }
    .segment { border-bottom: 1px solid #eef2f7; padding-bottom: 8px; line-height: 1.65; }
    .time { color: #64748b; font-size: 12px; margin-right: 6px; }
    pre { white-space: pre-wrap; word-break: break-word; margin: 0; line-height: 1.65; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    .hint { color: #64748b; font-size: 13px; line-height: 1.5; }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; }
      .content { height: 55vh; }
    }
  </style>
</head>
<body>
  <header>
    <h1>小红书直播转写</h1>
    <span id="connection" class="hint">未连接</span>
  </header>
  <main>
    <section class="panel">
      <label for="shareText">直播分享文本或链接</label>
      <textarea id="shareText" placeholder="粘贴小红书直播分享文本，或直接填 xhslink.com / livestream 链接"></textarea>
      <div class="row">
        <button id="startBtn">开始监听</button>
        <button id="stopBtn" class="danger" disabled>停止</button>
      </div>
      <div class="row">
        <input id="jobId" placeholder="或输入已有 job_id">
        <button id="connectBtn" class="secondary">连接</button>
      </div>
      <div class="status">
        <div class="metric"><b>任务</b><span id="job">-</span></div>
        <div class="metric"><b>状态</b><span id="status">-</span></div>
        <div class="metric"><b>分段</b><span id="chunks">0</span></div>
        <div class="metric"><b>转写片段</b><span id="count">0</span></div>
        <div class="metric"><b>结束原因</b><span id="reason">-</span></div>
        <div class="metric"><b>更新时间</b><span id="updated">-</span></div>
      </div>
      <p class="hint">页面通过 HTML5 EventSource 接收服务端流式更新。直播结束后可打开 job 目录里的 refined_note.md 查看精炼整理。</p>
    </section>
    <section>
      <div class="tabs">
        <button class="tab active" data-tab="segments">实时转写</button>
        <button class="tab" data-tab="note">滚动笔记</button>
      </div>
      <div id="segmentsPane" class="content segments"></div>
      <div id="notePane" class="content" style="display:none"><pre id="note"></pre></div>
    </section>
  </main>
  <script>
    let source = null;
    let currentJobId = null;

    const el = (id) => document.getElementById(id);
    const shareText = el("shareText");
    const jobIdInput = el("jobId");
    const startBtn = el("startBtn");
    const stopBtn = el("stopBtn");
    const connectBtn = el("connectBtn");
    const segmentsPane = el("segmentsPane");

    function extractUrl(text) {
      const match = text.match(/https?:\\/\\/(?:xhslink\\.com|www\\.xiaohongshu\\.com|xiaohongshu\\.com)\\S+/i);
      return match ? match[0].replace(/[，。！？）)]+$/g, "") : text.trim();
    }

    async function startJob() {
      const url = extractUrl(shareText.value);
      if (!url) return alert("请先粘贴直播分享文本或链接");
      startBtn.disabled = true;
      const response = await fetch("/jobs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({url, chunk_seconds: 60, language: "auto", asr_model: "small", asr_device: "auto", headless: false})
      });
      if (!response.ok) {
        startBtn.disabled = false;
        return alert(await response.text());
      }
      const job = await response.json();
      jobIdInput.value = job.id;
      connect(job.id);
    }

    async function stopJob() {
      if (!currentJobId) return;
      await fetch(`/jobs/${currentJobId}/stop`, {method: "POST"});
    }

    function connect(jobId) {
      if (!jobId) return alert("请输入 job_id");
      if (source) source.close();
      currentJobId = jobId;
      el("connection").textContent = "连接中";
      stopBtn.disabled = false;
      source = new EventSource(`/jobs/${jobId}/events`);
      source.addEventListener("job", (event) => {
        const data = JSON.parse(event.data);
        render(data);
        if (data.status === "stopped" || data.status === "failed") {
          source.close();
          el("connection").textContent = "已结束";
          startBtn.disabled = false;
          stopBtn.disabled = true;
        }
      });
      source.onerror = () => {
        el("connection").textContent = "连接断开，尝试重连";
      };
    }

    function render(data) {
      el("connection").textContent = "已连接";
      el("job").textContent = data.id || currentJobId || "-";
      el("status").textContent = data.status || "-";
      el("chunks").textContent = data.chunks_completed ?? 0;
      el("count").textContent = data.segments ? data.segments.length : 0;
      el("reason").textContent = data.ended_reason || "-";
      el("updated").textContent = data.updated_at || "-";
      el("note").textContent = data.note || "";
      segmentsPane.innerHTML = "";
      for (const segment of (data.segments || []).slice(-250)) {
        const item = document.createElement("div");
        item.className = "segment";
        item.innerHTML = `<span class="time">[${segment.start_text} - ${segment.end_text}]</span>${escapeHtml(segment.text)}`;
        segmentsPane.appendChild(item);
      }
      segmentsPane.scrollTop = segmentsPane.scrollHeight;
    }

    function escapeHtml(text) {
      return String(text).replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[ch]));
    }

    document.querySelectorAll(".tab").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        const tab = button.dataset.tab;
        el("segmentsPane").style.display = tab === "segments" ? "flex" : "none";
        el("notePane").style.display = tab === "note" ? "block" : "none";
      });
    });

    startBtn.addEventListener("click", startJob);
    stopBtn.addEventListener("click", stopJob);
    connectBtn.addEventListener("click", () => connect(jobIdInput.value.trim()));
  </script>
</body>
</html>"""
