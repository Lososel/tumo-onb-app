import json

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, Settings
from app.main import create_app
from app.sheet import matches, name_tokens, parse_tabs

MOCK = BACKEND_DIR / "data" / "mock_sheet.json"


@pytest.fixture
def make_client(tmp_path):
    def _make(mock_file=MOCK, **kw):
        settings = Settings(mock_file=mock_file, cache_file=tmp_path / "snapshot.json", **kw)
        return TestClient(create_app(settings))

    return _make


def lookup(c, query):
    return c.post("/api/schedule/lookup", json={"query": query}).json()


@pytest.mark.parametrize(
    "query",
    ["нуртас елмурат", "Елмұрат Нұртас", "ЕЛМУРАТ НУРТАС МЕДЕУУЛЫ", "нурт елму", "Елмурат  Нуртас"],
)
def test_matching_is_case_kazakh_order_and_prefix_insensitive(query):
    assert matches(name_tokens(query), name_tokens("Елмұрат Нұртас Медеуұлы"))


@pytest.mark.parametrize("query", ["нуртас нуртас", "нуртас иван", "ртас елмурат"])
def test_matching_rejects(query):
    assert not matches(name_tokens(query), name_tokens("Елмұрат Нұртас Медеуұлы"))


def test_lookup_found(make_client):
    with make_client() as c:
        body = lookup(c, "нурлан айбар")
        assert body["status"] == "ok"
        r = body["results"][0]
        assert r["full_name"] == "Айбар Нұрлан Серікұлы"
        assert r["schedule"] == "Вторник/Пятница 16:30-18:30"
        assert r["self_study_day"] == "Пятница"
        assert r["coach"] == "Aliya" and r["coach_email"] == "coach.aliya@example.com"
        assert r["stage_code"] == "self_study" and r["status_code"] == "coach_unchanged"
        assert r["note"] is None


def test_status_codes_and_kk_note(make_client):
    with make_client() as c:
        r = lookup(c, "асел толеген")["results"][0]
        assert r["status_code"] == "schedule_changed" and r["stage_code"] == "workshop"
        assert r["note_kk"].startswith("Жаңа")
        assert lookup(c, "тимур ахметов")["results"][0]["status_code"] == "coach_changed"
        assert lookup(c, "мадина ержанова")["results"][0]["status_code"] == "pending"


def test_lookup_states(make_client):
    with make_client() as c:
        assert lookup(c, "Айбар")["status"] == "need_full_name"
        assert lookup(c, "а б")["status"] == "need_full_name"
        assert lookup(c, "Иван Иванов")["status"] == "not_found"
        assert lookup(c, "данияр беков")["status"] == "inactive"
        assert lookup(c, "алия сер")["status"] == "too_many"  # vague query reveals nothing
        assert lookup(c, "алия серикова")["status"] == "ok"
        assert c.post("/api/schedule/lookup", json={"query": ""}).status_code == 422


def test_unknown_columns_are_never_kept():
    raw = {"Learners": [{"ФИО": "Иван Петров", "IIN": "000000000000", "Phone": "+77001234567", "Коуч": "X"}]}
    snap = parse_tabs(raw, source="test")
    dumped = snap.model_dump_json()
    assert "000000000000" not in dumped and "+77001234567" not in dumped
    assert snap.learners[0].coach == "X"


def test_bad_email_dropped():
    raw = {"Learners": [{"full_name": "Иван Петров", "coach_email": "not-an-email"}]}
    assert parse_tabs(raw, source="test").learners[0].coach_email == ""


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
    assert json.loads((tmp_path / "snapshot.json").read_text())["learners"][0]["coach"] == "Aliya"


def test_no_data_returns_503(make_client, tmp_path):
    with make_client(mock_file=tmp_path / "missing.json") as c:
        assert c.post("/api/schedule/lookup", json={"query": "A B"}).status_code == 503


def test_rate_limit(make_client):
    with make_client(lookup_rate_limit_per_minute=2) as c:
        for _ in range(2):
            assert c.post("/api/schedule/lookup", json={"query": "Иван Иванов"}).status_code == 200
        assert c.post("/api/schedule/lookup", json={"query": "Иван Иванов"}).status_code == 429


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
