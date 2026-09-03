from datetime import datetime, timezone

from redbook_stream_notes.notes import build_note, build_refined_note, extract_keywords
from redbook_stream_notes.schemas import TranscriptSegment


def test_extract_keywords_handles_chinese_terms():
    keywords = extract_keywords("今天讲直播运营 直播间 留存 转化 直播运营")
    assert "直播运营" in keywords
    assert "直播间" in keywords


def test_build_note_contains_timeline_and_transcript():
    segments = [
        TranscriptSegment(
            index=1,
            start=0,
            end=8,
            start_text="00:00:00.000",
            end_text="00:00:08.000",
            text="今天讲直播间转化的三个关键动作。",
        )
    ]
    note = build_note(segments, "https://example.com/live", datetime(2026, 5, 19, 1, 2, 3, tzinfo=timezone.utc))
    assert "# 直播笔记" in note
    assert "2026-05-19 09:02:03 CST" in note
    assert "## 时间线" in note
    assert "今天讲直播间转化" in note


def test_build_refined_note_contains_date():
    segments = [
        TranscriptSegment(
            index=1,
            start=0,
            end=8,
            start_text="00:00:00.000",
            end_text="00:00:08.000",
            text="今天讲资金流和半导体方向。",
        )
    ]
    note = build_refined_note(
        segments,
        "https://example.com/live",
        "直播已结束",
        datetime(2026, 5, 19, 1, 2, 3, tzinfo=timezone.utc),
    )
    assert "- 日期：2026-05-19 09:02:03 CST" in note


def test_build_refined_note_does_not_invent_unmentioned_topics():
    segments = [
        TranscriptSegment(
            index=1,
            start=0,
            end=8,
            start_text="00:00:00.000",
            end_text="00:00:08.000",
            text="今天重点看4143压力位和4129的21日均线，下午继续看资金流。",
        )
    ]
    note = build_refined_note(segments, "https://example.com/live", "直播已结束")
    assert "4143" in note
    assert "4129" in note
    assert "新能源车" not in note
    assert "锂矿" not in note
