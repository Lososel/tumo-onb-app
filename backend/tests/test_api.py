import json
import stat

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app

MOCK = BACKEND_DIR / "data" / "mock_sheet.json"
CARD_FIELDS = {
    "full_name", "schedule", "coach_name", "room", "default_email", "temp_password", "status_code", "status",
}


@pytest.fixture
def make_client(tmp_path):
    def _make(mock_file=MOCK, **kw):
        settings = Settings(mock_file=mock_file, cache_file=tmp_path / "snapshot.json", **kw)
        return TestClient(create_app(settings))

    return _make


def lookup(c, query):
    return c.post("/api/schedule/lookup", json={"query": query}).json()


def test_lookup_returns_schedule_card(make_client):
    with make_client() as c:
        body = lookup(c, "нурлан айбар")
        assert body["status"] == "ok" and len(body["results"]) == 1
        card = body["results"][0]
        assert set(card) == CARD_FIELDS
        assert card == {
            "full_name": "Айбар Нұрлан Серікұлы",
            "schedule": "Вторник/Пятница 16:30-18:30",
            "coach_name": "Aliya",
            "room": "Lab 2",
            "default_email": "aibar.nurlan@example.com",
            "temp_password": None,  # EXPOSE_TEMP_PASSWORD defaults to off
            "status_code": "active_schedule",
            "status": None,
        }


def test_all_tabs_are_searched(make_client):
    with make_client() as c:
        assert lookup(c, "асел толеген")["results"][0]["room"] == "Lab 1"  # tab "Поток 1", ru headers
        timur = lookup(c, "тимур ахметов")["results"][0]  # tab "Batch 2", en headers, other order
        assert (timur["coach_name"], timur["status_code"]) == ("Arman", "schedule_changed")
        assert lookup(c, "алия серикова")["results"][0]["room"] == "Lab 1"  # header-less tab
        pending = lookup(c, "мадина ержанова")["results"][0]
        assert pending["status_code"] == "schedule_pending" and pending["schedule"] is None


def test_duplicate_row_in_other_tab_is_ignored(make_client):
    with make_client() as c:
        results = lookup(c, "айбар нурлан")["results"]
        assert len(results) == 1 and results[0]["room"] == "Lab 2"


def test_lookup_states_and_result_cap(make_client):
    with make_client() as c:
        assert lookup(c, "Айбар")["status"] == "need_full_name"
        assert lookup(c, "а б")["status"] == "need_full_name"
        assert lookup(c, "Иван Иванов")["status"] == "not_found"
        assert lookup(c, "данияр беков")["status"] == "inactive"
        vague = lookup(c, "алия сер")  # 4 matches > cap of 3: nothing revealed
        assert vague["status"] == "too_many" and vague["results"] == []
        assert lookup(c, "алия серик")["status"] == "too_many"
        assert c.post("/api/schedule/lookup", json={"query": ""}).status_code == 422


def test_up_to_three_matches_are_returned(make_client, tmp_path):
    header = ["ФИО", "Расписание"]
    sheet = tmp_path / "sheet.json"
    sheet.write_text(json.dumps({"T": [header] + [[f"Иван Петров{s}", "Пн"] for s in ("", "ич", "ский")]}))
    with make_client(mock_file=sheet) as c:
        body = lookup(c, "иван петров")
        assert body["status"] == "ok" and len(body["results"]) == 3


def test_temp_password_hidden_by_default(make_client):
    with make_client() as c:
        body = lookup(c, "нурлан айбар")
        assert body["results"][0]["temp_password"] is None
        assert "Tumo-4821" not in json.dumps(body)


def test_temp_password_shown_when_enabled(make_client):
    with make_client(expose_temp_password=True) as c:
        assert lookup(c, "нурлан айбар")["results"][0]["temp_password"] == "Tumo-4821"


def test_expose_temp_password_env_parsing(monkeypatch):
    for value, expected in [("true", True), ("1", True), ("false", False), ("0", False), ("", False)]:
        monkeypatch.setenv("EXPOSE_TEMP_PASSWORD", value)
        assert Settings.from_env().expose_temp_password is expected
    monkeypatch.delenv("EXPOSE_TEMP_PASSWORD")
    assert Settings.from_env().expose_temp_password is False


def test_tumo_id_and_iin_never_in_responses(make_client, tmp_path):
    sheet = tmp_path / "sheet.json"
    sheet.write_text(
        json.dumps(
            {
                "T": [
                    ["ФИО", "Расписание", "TUMO ID", "ИИН", "Email коуча", "Пароль"],
                    ["Иван Петров", "Пн", "AST-9999", "000000000000", "c@example.com", "P-1"],
                ]
            }
        )
    )
    with make_client(mock_file=sheet, expose_temp_password=True) as c:
        raw = c.post("/api/schedule/lookup", json={"query": "иван петров"}).text
        assert "AST-9999" not in raw and "000000000000" not in raw
        assert "c@example.com" not in raw  # extra_info stays server-side
        assert set(json.loads(raw)["results"][0]) == CARD_FIELDS


def test_cache_file_is_owner_only(make_client, tmp_path):
    with make_client():
        pass
    mode = stat.S_IMODE((tmp_path / "snapshot.json").stat().st_mode)
    assert mode == 0o600


def test_falls_back_to_cache_when_source_fails(make_client, tmp_path):
    sheet = tmp_path / "sheet.json"
    sheet.write_text(MOCK.read_text(encoding="utf-8"), encoding="utf-8")
    with make_client(mock_file=sheet) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        sheet.write_text("{not json", encoding="utf-8")  # simulate the source breaking
        assert c.app.state.store.refresh() is False
        assert c.get("/api/health").json()["status"] == "degraded"
        assert lookup(c, "нурлан айбар")["status"] == "ok"

    # A fresh process with a broken source still serves the persisted snapshot.
    with make_client(mock_file=sheet) as c:
        assert c.get("/api/health").json()["learners_cached"] == 9
        assert lookup(c, "нурлан айбар")["status"] == "ok"


def test_no_data_answers_unavailable_not_5xx(make_client, tmp_path):
    with make_client(mock_file=tmp_path / "missing.json") as c:
        r = c.post("/api/schedule/lookup", json={"query": "A B"})
        assert r.status_code == 200 and r.json()["status"] == "unavailable"
        assert c.get("/api/health").json()["status"] == "no_data"


def test_rate_limit(make_client):
    with make_client(lookup_rate_limit_per_minute=2) as c:
        for _ in range(2):
            assert c.post("/api/schedule/lookup", json={"query": "Иван Иванов"}).status_code == 200
        assert c.post("/api/schedule/lookup", json={"query": "Иван Иванов"}).status_code == 429


def test_rate_limit_uses_proxy_client_ip(make_client):
    def post(c, xff):
        return c.post("/api/schedule/lookup", json={"query": "Иван Иванов"}, headers={"X-Forwarded-For": xff})

    with make_client(lookup_rate_limit_per_minute=1, proxy_hops=1) as c:
        assert post(c, "203.0.113.1").status_code == 200
        assert post(c, "203.0.113.2").status_code == 200  # a different user behind the same proxy
        assert post(c, "203.0.113.1").status_code == 429
        # A forged left-most entry doesn't help: the proxy-appended right-most entry is used.
        assert post(c, "198.51.100.9, 203.0.113.1").status_code == 429


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
    with make_client(static_dir=dist) as c:
        assert c.get("/").text == "<html>app</html>"
        assert c.get("/assets/a.js").text == "console.log(1)"
        assert c.get("/api/nope").status_code == 404
