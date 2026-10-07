"""Startup and lookups must survive broken Google config, auth/network errors and bad env values."""

import json
import sys
import types

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app
from app.services.sheets import SheetsConfigError, load_credentials_file, parse_credentials_json
from app.sources import GoogleSheetsSource

FAKE_KEY_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC-fake-key-material"
SERVICE_ACCOUNT = {
    "type": "service_account",
    "project_id": "demo",
    "client_email": "reader@demo.iam.gserviceaccount.com",
    "private_key": f"-----BEGIN PRIVATE KEY-----\n{FAKE_KEY_BODY}\n-----END PRIVATE KEY-----\n",
    "token_uri": "https://oauth2.googleapis.com/token",
}


# ---------- GOOGLE_CREDENTIALS_JSON parsing ----------


def test_parse_valid_json():
    assert parse_credentials_json(json.dumps(SERVICE_ACCOUNT)) == SERVICE_ACCOUNT


def test_escaped_newlines_in_private_key_are_restored():
    # Dashboards often store the key with literal backslash-n instead of newlines.
    broken = dict(SERVICE_ACCOUNT, private_key=SERVICE_ACCOUNT["private_key"].replace("\n", "\\n"))
    info = parse_credentials_json(json.dumps(broken))
    assert info["private_key"] == SERVICE_ACCOUNT["private_key"]
    assert "\\n" not in info["private_key"]


def test_real_newlines_pasted_inside_the_json_string():
    raw = json.dumps(SERVICE_ACCOUNT).replace("\\n", "\n")  # invalid strict JSON, common paste
    assert parse_credentials_json(raw)["private_key"] == SERVICE_ACCOUNT["private_key"]


def test_json_wrapped_in_quotes():
    assert parse_credentials_json(json.dumps(json.dumps(SERVICE_ACCOUNT)))["client_email"] == (
        SERVICE_ACCOUNT["client_email"]
    )


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("", "empty"),
        ('{"type": "service_account", "private_key": "' + FAKE_KEY_BODY, "not valid JSON"),
        ("[1, 2]", "JSON object"),
        (json.dumps({"type": "authorized_user", "private_key": FAKE_KEY_BODY}), "not a service-account key"),
    ],
)
def test_invalid_json_errors_never_leak_key_material(raw, fragment):
    with pytest.raises(SheetsConfigError) as exc:
        parse_credentials_json(raw)
    assert fragment in str(exc.value)
    assert FAKE_KEY_BODY not in str(exc.value)


def test_missing_credentials_file(tmp_path):
    with pytest.raises(SheetsConfigError, match="not found"):
        load_credentials_file(tmp_path / "nope.json")


# ---------- startup never crashes ----------


@pytest.fixture
def make_client(tmp_path):
    def _make(**kw):
        kw.setdefault("cache_file", tmp_path / "snapshot.json")
        return TestClient(create_app(Settings(**kw)))

    return _make


def lookup(c, q="нурлан айбар"):
    return c.post("/api/schedule/lookup", json={"query": q})


def test_google_without_sheet_id_starts_and_reports(make_client):
    with make_client(data_source="google", google_sheet_id="") as c:  # used to raise at import
        health = c.get("/api/health").json()
        assert health["status"] == "no_data"
        assert "GOOGLE_SHEET_ID is not set" in health["last_sync_error"]
        r = lookup(c)
        assert r.status_code == 200 and r.json()["status"] == "unavailable"


def test_google_with_broken_credentials_json_starts(make_client):
    with make_client(data_source="google", google_sheet_id="sheet123",
                     google_credentials_json='{"private_key": "' + FAKE_KEY_BODY) as c:
        health = c.get("/api/health").json()
        assert "not valid JSON" in health["last_sync_error"]
        assert FAKE_KEY_BODY not in json.dumps(health)
        assert lookup(c).json()["status"] == "unavailable"


def test_google_with_missing_credentials_file_starts(make_client, tmp_path):
    with make_client(data_source="google", google_sheet_id="sheet123",
                     google_credentials_file=tmp_path / "missing.json") as c:
        assert "credentials file not found" in c.get("/api/health").json()["last_sync_error"]


@pytest.fixture
def fake_gspread(monkeypatch):
    """A gspread stand-in whose API calls fail like an auth/permission or network error."""

    class APIError(Exception):
        pass

    class Client:
        def set_timeout(self, _):
            pass

        def open_by_key(self, key):
            raise APIError(f"403 caller does not have permission for {key}")

    module = types.SimpleNamespace(service_account_from_dict=lambda info, scopes: Client())
    monkeypatch.setitem(sys.modules, "gspread", module)
    return APIError


def test_auth_error_during_sync_keeps_app_up(make_client, fake_gspread):
    creds = json.dumps(SERVICE_ACCOUNT)
    with make_client(data_source="google", google_sheet_id="sheet123", google_credentials_json=creds) as c:
        health = c.get("/api/health").json()
        assert health["status"] == "no_data"
        assert health["last_sync_error"] == "APIError"  # non-config errors expose only the type
        assert lookup(c).status_code == 200


def test_auth_error_falls_back_to_cached_snapshot(make_client, fake_gspread, tmp_path):
    cache = tmp_path / "snapshot.json"
    with make_client(cache_file=cache):  # a healthy mock run writes the cache
        pass
    creds = json.dumps(SERVICE_ACCOUNT)
    with make_client(data_source="google", google_sheet_id="sheet123", google_credentials_json=creds,
                     cache_file=cache) as c:
        assert lookup(c).json()["status"] == "ok"  # served from the cache
        assert c.app.state.store.refresh() is False  # live sync still failing
        assert c.get("/api/health").json()["status"] == "degraded"
        assert lookup(c).json()["status"] == "ok"


def test_opt_in_mock_fallback_is_served_but_never_cached(make_client, tmp_path):
    cache = tmp_path / "snapshot.json"
    with make_client(data_source="google", google_sheet_id="", fallback_to_mock=True, cache_file=cache) as c:
        assert lookup(c).json()["status"] == "ok"
        health = c.get("/api/health").json()
        assert (health["status"], health["source"]) == ("degraded", "mock-fallback")
    assert not cache.exists()  # fake data must never replace real data after a restart


def test_mock_fallback_off_by_default():
    assert Settings().fallback_to_mock is False


def test_invalid_numeric_env_values_do_not_crash(monkeypatch):
    monkeypatch.setenv("SYNC_INTERVAL_SECONDS", "5m")
    monkeypatch.setenv("LOOKUP_RATE_LIMIT_PER_MINUTE", "lots")
    monkeypatch.setenv("PROXY_HOPS", "one")
    s = Settings.from_env()
    assert (s.sync_interval_seconds, s.lookup_rate_limit_per_minute, s.proxy_hops) == (300, 30, 0)


def test_credentials_json_env_is_read(monkeypatch):
    monkeypatch.setenv("GOOGLE_CREDENTIALS_JSON", json.dumps(SERVICE_ACCOUNT))
    s = Settings.from_env()
    info = parse_credentials_json(s.google_credentials_json)
    assert info["client_email"] == SERVICE_ACCOUNT["client_email"]
    assert FAKE_KEY_BODY not in repr(s)  # never printed with the settings


def test_unexpected_lookup_error_answers_unavailable(make_client, monkeypatch):
    with make_client(mock_file=BACKEND_DIR / "data" / "mock_sheet.json") as c:
        def boom(_tokens):
            raise RuntimeError("index corrupted")

        monkeypatch.setattr(c.app.state.store, "search", boom)
        r = lookup(c)
        assert r.status_code == 200 and r.json() == {"status": "unavailable", "results": [],
                                                      "data_updated_at": None}


def test_google_source_rejects_malformed_private_key(monkeypatch):
    pytest.importorskip("google.oauth2.service_account")
    source = GoogleSheetsSource(BACKEND_DIR / "unused.json", "sheet123",
                                credentials_json=json.dumps(SERVICE_ACCOUNT))
    with pytest.raises(SheetsConfigError, match="key rejected"):
        source.fetch()
