from redbook_stream_notes.notes import build_note, extract_keywords
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
    note = build_note(segments, "https://example.com/live")
    assert "# 直播笔记" in note
    assert "## 时间线" in note
    assert "今天讲直播间转化" in note
