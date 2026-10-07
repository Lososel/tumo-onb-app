"""Security hardening: data minimization, anti-scraping limits, strict queries, HTTP headers."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

PUBLIC_FIELDS = {
    "full_name", "schedule", "coach_name", "coach_email", "room", "default_email", "temp_password",
    "status_code", "status",
}

# A sheet row full of things that must never leave the server.
SENSITIVE = {
    "ФИО родителя": "Родителева Мария Ивановна",
    "Номер родителя": "+7 701 111 22 33",
    "почта родителя": "parent.private@gmail.com",
    "Номер ребенка": "+7 702 444 55 66",
    "почта ребенка": "kid.private@mail.ru",
    "ДР ребенка": "05.05.2012",
    "ИИН ребенка": "120505123456",
    "ИИН родителя": "850101654321",
    "Адрес": "ул. Секретная, 1",
    "TUMO ID": "AST-SECRET-77",
}


@pytest.fixture
def sheet(tmp_path):
    header = ["ФИО ребенка", "Расписание", "Коуч", "Зона", "Почта TUMO", *SENSITIVE]
    second = {**SENSITIVE, "TUMO ID": "AST-SECRET-78"}  # distinct ID: same ID means same student
    rows = [
        header,
        ["Иванова Анна", "Пн/Чт 10:30-12:30", "Alinur", "WR 2", "anna.ivanova@tumo.world",
         *SENSITIVE.values()],
        ["Смирнов Олег", "Вт/Пт 14:30-16:30", "Nazym", "WR 3", "oleg.private@gmail.com",
         *second.values()],
    ]
    path = tmp_path / "sheet.json"
    path.write_text(json.dumps({"4 поток": rows}, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def make_client(sheet, tmp_path):
    def _make(**kw):
        kw.setdefault("lookup_rate_limit_per_minute", 0)
        return TestClient(create_app(Settings(mock_file=sheet, cache_file=tmp_path / "c.json", **kw)))

    return _make


def lookup(c, q, **headers):
    return c.post("/api/schedule/lookup", json={"query": q}, headers=headers)


# ---------- 1. data minimization ----------


def test_response_contains_only_public_fields(make_client):
    with make_client() as c:
        (card,) = lookup(c, "Иванова Анна").json()["results"]
        assert set(card) == PUBLIC_FIELDS
        assert card["temp_password"] is None  # EXPOSE_TEMP_PASSWORD is off by default


def test_sensitive_values_never_appear_in_any_response_or_cache(make_client, tmp_path):
    with make_client(expose_temp_password=True) as c:
        raw = lookup(c, "Иванова Анна").text + lookup(c, "Смирнов Олег").text + c.get("/api/health").text
    cache = (tmp_path / "c.json").read_text(encoding="utf-8")
    for column, value in SENSITIVE.items():
        assert value not in raw, f"{column} leaked in a response"
        assert "AST-SECRET-78" not in raw
        if column != "TUMO ID":  # kept server-side for de-duplication only
            assert value not in cache, f"{column} stored in the cache"


def test_only_tumo_world_student_emails_are_shown(make_client):
    with make_client() as c:
        assert lookup(c, "Иванова Анна").json()["results"][0]["default_email"] == "anna.ivanova@tumo.world"
        # A personal Gmail typed into the TUMO-email column is withheld, not published.
        assert lookup(c, "Смирнов Олег").json()["results"][0]["default_email"] == "Уточняется"


def test_student_email_domains_are_configurable(make_client, monkeypatch):
    monkeypatch.setenv("STUDENT_EMAIL_DOMAINS", "tumo.world, @Example.org")
    assert Settings.from_env().student_email_domains == ("tumo.world", "example.org")
    with make_client(student_email_domains=("gmail.com",)) as c:
        assert lookup(c, "Смирнов Олег").json()["results"][0]["default_email"] == "oleg.private@gmail.com"


# ---------- 2. rate limiting ----------


def test_default_limit_is_five_per_minute(make_client):
    assert Settings().lookup_rate_limit_per_minute == 5
    with make_client(lookup_rate_limit_per_minute=5) as c:
        for _ in range(5):
            assert lookup(c, "Иванова Анна").status_code == 200
        r = lookup(c, "Иванова Анна")
        assert r.status_code == 429
        assert r.json()["detail"] == "Too Many Requests. Please wait a minute before searching again."
        assert 1 <= int(r.headers["Retry-After"]) <= 61


def test_limit_is_per_client_ip_behind_proxy(make_client):
    with make_client(lookup_rate_limit_per_minute=5, proxy_hops=1) as c:
        for _ in range(5):
            assert lookup(c, "Иванова Анна", **{"X-Forwarded-For": "203.0.113.1"}).status_code == 200
        assert lookup(c, "Иванова Анна", **{"X-Forwarded-For": "203.0.113.1"}).status_code == 429
        assert lookup(c, "Иванова Анна", **{"X-Forwarded-For": "203.0.113.2"}).status_code == 200
        # Rotating a forged left-hand entry doesn't reset the limit.
        assert lookup(c, "x", **{"X-Forwarded-For": "1.2.3.4, 203.0.113.1"}).status_code == 429


# ---------- 3. strict queries ----------


@pytest.mark.parametrize("query", ["А Е", "Ан Ли", "Анна Ли", "Иванова", "Ив Ан", "аа бб вв"])
def test_queries_need_two_words_of_three_letters(make_client, query):
    with make_client() as c:
        assert lookup(c, query).json() == {"status": "need_full_name", "results": [],
                                           "data_updated_at": lookup(c, query).json()["data_updated_at"]}


def test_two_three_letter_words_are_enough(make_client):
    with make_client() as c:
        assert lookup(c, "Ива Анн").json()["status"] == "ok"  # prefixes of 3+ letters still work
        assert lookup(c, "Иванова Анна").json()["status"] == "ok"


def test_overlong_query_is_rejected(make_client):
    with make_client() as c:
        assert lookup(c, "А" * 121).status_code == 422


# ---------- 4. security headers ----------

EXPECTED_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def assert_security_headers(r):
    for name, value in EXPECTED_HEADERS.items():
        assert r.headers.get(name) == value, name
    csp = r.headers["content-security-policy"]
    required = ("default-src 'self'", "script-src 'self'", "frame-ancestors 'none'", "object-src 'none'")
    for directive in required:
        assert directive in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "max-age=" in r.headers["strict-transport-security"]


def test_security_headers_on_api_errors_and_rate_limits(make_client):
    with make_client(lookup_rate_limit_per_minute=1) as c:
        ok = lookup(c, "Иванова Анна")
        limited = lookup(c, "Иванова Анна")
        for r in (ok, limited, c.get("/api/health"), c.get("/api/does-not-exist"),
                  c.post("/api/schedule/lookup", json={})):
            assert_security_headers(r)
            assert r.headers["cache-control"] == "no-store"
        assert limited.status_code == 429


def test_security_headers_on_frontend(make_client, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    with make_client(static_dir=dist) as c:
        r = c.get("/")
        assert r.text == "<html>app</html>"
        assert_security_headers(r)
        # With docs off, these paths fall through to the SPA page — never the API schema.
        assert '"openapi"' not in c.get("/openapi.json").text
        assert "swagger" not in c.get("/docs").text.lower()


def test_api_docs_disabled_by_default(make_client):
    with make_client() as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
    with make_client(enable_api_docs=True) as c:
        assert c.get("/openapi.json").status_code == 200


# ---------- 5. limiter memory, proxy check, hostile workbooks ----------


def test_limiter_memory_stays_bounded_under_ip_flood():
    from app.core.rate_limit import RateLimiter

    limiter = RateLimiter(5, max_keys=100)
    for i in range(1_000):
        limiter.check(f"10.0.{i // 256}.{i % 256}")
    assert len(limiter._hits) <= 100
    # The most recent clients are still counted after a prune.
    for _ in range(4):
        limiter.check("10.0.3.231")
    with pytest.raises(Exception):
        limiter.check("10.0.3.231")


def test_limiter_forgets_idle_clients(monkeypatch):
    from app.core import rate_limit

    now = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: now[0])
    limiter = rate_limit.RateLimiter(5, max_keys=10)
    for i in range(10):
        limiter.check(f"old-{i}")
    now[0] += 61
    limiter.check("new")  # 11th key triggers a prune: every idle client is dropped
    assert set(limiter._hits) == {"new"}


def test_proxy_hops_mismatch_is_logged_once_without_addresses(make_client, caplog, monkeypatch):
    from app.api.endpoints import schedule

    monkeypatch.setattr(schedule, "_proxy_shape_logged", False)
    with make_client(proxy_hops=1) as c, caplog.at_level("INFO"):
        lookup(c, "Иванова Анна", **{"X-Forwarded-For": "198.51.100.7, 203.0.113.9"})
        lookup(c, "Иванова Анна", **{"X-Forwarded-For": "198.51.100.7"})
    lines = [r.getMessage() for r in caplog.records if "X-Forwarded-For" in r.getMessage()]
    assert lines == ["First lookup: X-Forwarded-For has 2 entries, PROXY_HOPS=1 (check PROXY_HOPS)"]
    assert "198.51.100.7" not in caplog.text and "203.0.113.9" not in caplog.text


def test_xml_bomb_workbook_is_rejected_not_expanded():
    import io
    import zipfile

    import openpyxl
    from openpyxl.xml import DEFUSEDXML

    from app.services.sheets import SheetsConfigError, xlsx_to_tabs

    assert DEFUSEDXML, "defusedxml must be installed so openpyxl refuses entity expansion"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "x"
    buf = io.BytesIO()
    wb.save(buf)
    entities = "".join(f'<!ENTITY {n} "{("&" + p + ";") * 10}">' for p, n in zip("abcdefgh", "bcdefghi"))
    sheet = (
        '<?xml version="1.0"?>{doctype}'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1"><c r="A1" t="inlineStr"><is><t>{text}</t></is></c></row></sheetData></worksheet>'
    )

    def workbook(sheet_xml: str) -> bytes:
        src, out = zipfile.ZipFile(io.BytesIO(buf.getvalue())), io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for item in src.namelist():
                z.writestr(item, sheet_xml if item == "xl/worksheets/sheet1.xml" else src.read(item))
        return out.getvalue()

    # Control: the same hand-built sheet without entities reads fine.
    plain = workbook(sheet.format(doctype="", text="Иванова Анна"))
    assert xlsx_to_tabs(plain) == {"Sheet": [["Иванова Анна"]]}
    # The bomb (one cell expanding to a billion characters) is refused before any expansion; the
    # store records the failed sync and keeps serving the last good snapshot.
    bomb = sheet.format(doctype=f'<!DOCTYPE x [<!ENTITY a "aaaaaaaaaa">{entities}]>', text="&i;")
    with pytest.raises(SheetsConfigError):
        xlsx_to_tabs(workbook(bomb))
