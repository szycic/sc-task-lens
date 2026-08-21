import pytest
from fastapi.testclient import TestClient
import io
from PIL import Image
from sc_task_lens.main import app

client = TestClient(app)

def test_root_index_and_tab_paths():
    for path in ["/", "/inbox", "/notion", "/ai", "/admin"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "Task Lens" in response.text


def test_inbox_stats_endpoint():
    res = client.get("/api/inbox/stats")
    assert res.status_code == 200
    data = res.json()
    assert "counts" in data
    assert "last_synced_at" in data
    assert "PENDING" in data["counts"]


def test_upload_and_operations():
    # 1. Create a dummy image in memory
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)

    # 2. Upload file
    upload_res = client.post(
        "/api/inbox/upload",
        files={"file": ("test_screenshot.png", img_byte_arr, "image/png")}
    )
    assert upload_res.status_code == 200
    data = upload_res.json()
    assert data["success"] is True
    candidate_id = data["candidate_id"]

    # 3. Retrieve candidate details
    cand_res = client.get(f"/api/inbox/candidates/{candidate_id}")
    assert cand_res.status_code == 200
    cand_data = cand_res.json()
    assert cand_data["title"] == "Processing screenshot..."
    assert cand_data["status"] == "PENDING"

    # 4. Update candidate
    update_res = client.put(
        f"/api/inbox/candidates/{candidate_id}",
        json={
            "title": "Fix alignment bug on Login view",
            "summary": "AI extracted task summary",
            "priority": "HIGH",
            "project": "Work"
        }
    )
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Fix alignment bug on Login view"
    assert update_res.json()["priority"] == "HIGH"

    # 5. Ignore candidate
    ignore_res = client.post(f"/api/inbox/candidates/{candidate_id}/ignore")
    assert ignore_res.status_code == 200
    assert ignore_res.json()["status"] == "IGNORED"

    # 6. Unignore candidate
    unignore_res = client.post(f"/api/inbox/candidates/{candidate_id}/unignore")
    assert unignore_res.status_code == 200
    assert unignore_res.json()["status"] == "PENDING"


def test_sync_updates_websocket():
    with client.websocket_connect("/api/inbox/ws/sync-updates") as websocket:
        data = websocket.receive_json()
        assert data.get("event") == "connected"
        assert "stats" in data


def test_service_worker_route():
    res = client.get("/sw.js")
    assert res.status_code == 200
    assert "application/javascript" in res.headers["content-type"]

