import json

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, Settings
from app.main import create_app
from app.sheet import normalize_name, parse_tabs


@pytest.fixture
def make_client(tmp_path):
    def _make(mock_file=BACKEND_DIR / "data" / "mock_sheet.json", **kw):
        settings = Settings(mock_file=mock_file, cache_file=tmp_path / "snapshot.json", **kw)
        return TestClient(create_app(settings))

    return _make


def test_lookup_found_post(make_client):
    with make_client() as c:
        r = c.post("/api/students/lookup", json={"first_name": "aruzhan", "last_name": "SMAGULOVA"})
        body = r.json()
        assert r.status_code == 200 and body["status"] == "ok"
        s = body["students"][0]
        assert s["first_name"] == "Aruzhan"
        assert s["self_study"] == {"days": "Mon, Wed", "time": "15:00–17:00"}
        assert s["workshops"][0]["name"] == "2D Animation"
        # Workshop link wins over the default link
        assert s["links"]["whatsapp"] == "https://chat.whatsapp.com/example-animation"


def test_lookup_get_full_name_reversed_order(make_client):
    with make_client() as c:
        body = c.get("/api/students/lookup", params={"full_name": "Bekov  Daniyar"}).json()
        assert body["status"] == "ok"
        assert [w["name"] for w in body["students"][0]["workshops"]] == [
            "Programming: Python Basics",
            "Music Production",
        ]


def test_cyrillic_and_default_whatsapp(make_client):
    with make_client() as c:
        body = c.post("/api/students/lookup", json={"full_name": "аружан касымова"}).json()
        assert body["status"] == "ok"
        assert body["students"][0]["workshops"][0]["room"] is None
        assert body["students"][0]["links"]["whatsapp"] == "https://chat.whatsapp.com/example-tumo-astana"


def test_not_found_and_inactive(make_client):
    with make_client() as c:
        assert c.post("/api/students/lookup", json={"full_name": "Nobody Here"}).json()["status"] == "not_found"
        body = c.post("/api/students/lookup", json={"full_name": "Timur Akhmetov"}).json()
        assert body["status"] == "inactive" and body["students"] == []


def test_validation(make_client):
    with make_client() as c:
        assert c.post("/api/students/lookup", json={"first_name": "Only"}).status_code == 422
        assert c.get("/api/students/lookup").status_code == 422


def test_unknown_columns_are_never_kept():
    raw = {
        "Students": [{"First Name": "A", "Last Name": "B", "IIN": "000000000000", "Phone": "+7"}],
        "Workshops": [],
        "Links": [],
    }
    dumped = parse_tabs(raw, source="test").model_dump_json()
    assert "000000000000" not in dumped and "+7" not in dumped
    assert normalize_name("A B") in dumped


def test_falls_back_to_cache_when_source_fails(make_client, tmp_path):
    sheet = tmp_path / "sheet.json"
    sheet.write_text((BACKEND_DIR / "data" / "mock_sheet.json").read_text(encoding="utf-8"), encoding="utf-8")
    with make_client(mock_file=sheet) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        sheet.write_text("{not json", encoding="utf-8")  # simulate the source breaking
        assert c.app.state.store.refresh() is False
        assert c.get("/api/health").json()["status"] == "degraded"
        assert c.post("/api/students/lookup", json={"full_name": "Aruzhan Smagulova"}).json()["status"] == "ok"

    # A fresh process with a broken source still serves the persisted snapshot.
    with make_client(mock_file=sheet) as c:
        health = c.get("/api/health").json()
        assert health["students_cached"] == 5
        assert c.post("/api/students/lookup", json={"full_name": "Aruzhan Smagulova"}).json()["status"] == "ok"
    assert "Smagulova" in json.loads((tmp_path / "snapshot.json").read_text())["students"][0]["last_name"]


def test_no_data_returns_503(make_client, tmp_path):
    with make_client(mock_file=tmp_path / "missing.json") as c:
        assert c.post("/api/students/lookup", json={"full_name": "A B"}).status_code == 503


def test_rate_limit(make_client):
    with make_client(lookup_rate_limit_per_minute=2) as c:
        for _ in range(2):
            assert c.post("/api/students/lookup", json={"full_name": "A B"}).status_code == 200
        assert c.post("/api/students/lookup", json={"full_name": "A B"}).status_code == 429


def test_admin_refresh_disabled_by_default(make_client):
    with make_client() as c:
        assert c.post("/api/admin/refresh").status_code == 404
    with make_client(admin_token="s3cret") as c:
        assert c.post("/api/admin/refresh", headers={"X-Admin-Token": "nope"}).status_code == 404
        assert c.post("/api/admin/refresh", headers={"X-Admin-Token": "s3cret"}).json()["status"] == "ok"


def test_serves_spa_when_built(make_client, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    (dist / "favicon.svg").write_text("<svg/>")
    with make_client(static_dir=dist) as c:
        assert c.get("/dashboard").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        assert c.get("/api/nope").status_code == 404
        assert c.get("/api/health").json()["status"] == "ok"
