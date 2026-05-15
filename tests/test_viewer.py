from fastapi.testclient import TestClient

from redbook_stream_notes.main import app


def test_viewer_page_contains_streaming_ui():
    client = TestClient(app)
    response = client.get("/viewer")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "小红书直播转写" in response.text
    assert "EventSource" in response.text
    assert "/jobs/${jobId}/events" in response.text


def test_recent_jobs_endpoint_returns_list():
    client = TestClient(app)
    response = client.get("/jobs/recent")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_unknown_job_events_returns_404():
    client = TestClient(app)
    response = client.get("/jobs/not-a-real-job/events")
    assert response.status_code == 404
