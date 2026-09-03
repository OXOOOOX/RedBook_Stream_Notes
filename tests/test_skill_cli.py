import json
from pathlib import Path

import pytest

from scripts import redbook


@pytest.mark.parametrize(
    ("share_text", "expected"),
    [
        ("正在直播，点击（https://xhslink.com/example）。", "https://xhslink.com/example"),
        ("查看（https://xhslink.com/example），点击打开", "https://xhslink.com/example"),
        (
            "直播链接：https://www.xiaohongshu.com/livestream/example?share_id=abc&source=copy%20link，",
            "https://www.xiaohongshu.com/livestream/example?share_id=abc&source=copy%20link",
        ),
        ("查看 https://live.xiaohongshu.com/example！", "https://live.xiaohongshu.com/example"),
        (
            "https://xhslink.com/example 再次分享 https://xhslink.com/example",
            "https://xhslink.com/example",
        ),
    ],
)
def test_extract_shared_link_preserves_target(share_text, expected):
    assert redbook.extract_url(share_text) == expected


@pytest.mark.parametrize(
    "share_text",
    [
        "https://xhslink.com.evil.example/live",
        "https://notxiaohongshu.com/live",
        "https://xhslink.com@evil.example/live",
        "https://user:password@xhslink.com/live",
        "https://xhslink.com/one https://www.xiaohongshu.com/two",
        "没有直播链接",
    ],
)
def test_extract_shared_link_rejects_lookalikes_and_ambiguous_targets(share_text):
    with pytest.raises(ValueError, match="exactly one"):
        redbook.extract_url(share_text)


@pytest.mark.parametrize("status", ["stopped", "failed", "stopping"])
def test_stop_does_not_post_when_job_already_stopping_or_terminal(monkeypatch, capsys, status):
    calls = []
    snapshot = {"id": "existing-job", "status": status, "segments": []}

    def fake_request(api, path, *, method="GET", **kwargs):
        calls.append((api, path, method))
        assert method == "GET", "Do not mutate a terminal or stopping job"
        return snapshot

    monkeypatch.setattr(redbook, "request_json", fake_request)

    assert redbook.main(["stop", "existing-job"]) == 0
    assert calls == [("http://127.0.0.1:8000", "/jobs/existing-job", "GET")]
    assert json.loads(capsys.readouterr().out) == snapshot


@pytest.mark.parametrize("status", ["starting", "listening", "stopping"])
def test_create_refuses_recent_active_job_without_post(monkeypatch, capsys, status):
    calls = []

    def fake_request(api, path, *, method="GET", **kwargs):
        calls.append((path, method))
        assert method == "GET", "An existing active job must prevent creation"
        assert path == "/jobs/recent"
        return [{"id": "finished", "status": "stopped"}, {"id": "active", "status": status}]

    monkeypatch.setattr(redbook, "request_json", fake_request)

    assert redbook.main(["create", "--url", "https://xhslink.com/example"]) == 1
    assert calls == [("/jobs/recent", "GET")]
    assert "active job already exists" in capsys.readouterr().err


def sample_snapshot(status="stopped", segment_count=125):
    return {
        "id": "export-job",
        "url": "https://xhslink.com/example?share_id=keep-this",
        "status": status,
        "note": "# 滚动笔记\n\n此草稿不能代替全部原文。\n",
        "segments": [
            {
                "index": index + 1,
                "start": float(index),
                "end": float(index + 1),
                "start_text": f"00:{index // 60:02d}:{index % 60:02d}.000",
                "end_text": f"00:{(index + 1) // 60:02d}:{(index + 1) % 60:02d}.000",
                "text": f"第 {index + 1:03d} 条完整转写，保留原文与数字。",
            }
            for index in range(segment_count)
        ],
    }


@pytest.mark.parametrize(("status", "partial"), [("stopped", False), ("listening", True)])
def test_export_retains_every_segment_beyond_rolling_note_limit(monkeypatch, capsys, tmp_path, status, partial):
    snapshot = sample_snapshot(status=status)
    calls = []

    def fake_request(api, path, *, method="GET", **kwargs):
        calls.append((path, method))
        assert method == "GET"
        return snapshot

    monkeypatch.setattr(redbook, "request_json", fake_request)
    destination = tmp_path / "完整导出"

    assert redbook.main(["export", "export-job", "--output", str(destination)]) == 0
    assert calls == [("/jobs/export-job", "GET")]
    summary = json.loads(capsys.readouterr().out)
    assert summary["segments"] == 125
    assert summary["partial"] is partial
    assert Path(summary["directory"]) == destination.resolve()
    assert json.loads((destination / "snapshot.json").read_text(encoding="utf-8")) == snapshot
    assert (destination / "note.md").read_text(encoding="utf-8") == snapshot["note"]
    transcript_lines = (destination / "transcript.md").read_text(encoding="utf-8").splitlines()
    assert [line for line in transcript_lines if line.startswith("- [")] == [
        f"- [{segment['start_text']} - {segment['end_text']}] {segment['text']}"
        for segment in snapshot["segments"]
    ]


def test_export_refuses_existing_directory_and_preserves_its_contents(monkeypatch, capsys, tmp_path):
    destination = tmp_path / "existing-export"
    destination.mkdir()
    existing = destination / "snapshot.json"
    existing.write_text("用户已有内容\n", encoding="utf-8")
    calls = []

    def fake_request(api, path, *, method="GET", **kwargs):
        calls.append((path, method))
        assert method == "GET"
        return sample_snapshot(segment_count=1)

    monkeypatch.setattr(redbook, "request_json", fake_request)

    assert redbook.main(["export", "export-job", "--output", str(destination)]) == 1
    assert calls == [("/jobs/export-job", "GET")]
    assert "Error:" in capsys.readouterr().err
    assert existing.read_text(encoding="utf-8") == "用户已有内容\n"
    assert sorted(path.name for path in destination.iterdir()) == ["snapshot.json"]
