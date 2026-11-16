"""The console is a static page on another origin, so CORS decides whether the
product can use its own API. These tests exist because the failure is invisible
from the server side: curl works, and only a browser is refused.
"""
from fastapi.testclient import TestClient

from app.main import app

PAGES = "https://tshepisofrominnostation.github.io"


def _client():
    return TestClient(app)


def test_console_origin_is_allowed_on_a_simple_request():
    r = _client().get("/health", headers={"Origin": PAGES})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == PAGES


def test_preflight_for_posting_a_ticket_is_allowed():
    r = _client().options(
        "/tickets",
        headers={
            "Origin": PAGES,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == PAGES
    assert "POST" in r.headers.get("access-control-allow-methods", "")


def test_localhost_is_allowed_so_the_page_can_be_developed_offline():
    r = _client().get("/health", headers={"Origin": "http://localhost:8000"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8000"


def test_an_unrelated_site_is_refused():
    """A wildcard here would let any web page post tickets to a hospital system."""
    r = _client().get("/health", headers={"Origin": "https://evil.example.com"})
    assert r.headers.get("access-control-allow-origin") is None


def test_requests_without_an_origin_still_work():
    """Server-to-server callers send no Origin and must not be affected."""
    r = _client().get("/health")
    assert r.status_code == 200
