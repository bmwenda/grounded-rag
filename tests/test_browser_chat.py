"""Browser chat assets are served alongside the versioned API."""

from fastapi.testclient import TestClient

from src.api.main import create_app


def test_chat_page_and_assets_are_served() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert 'id="auth-form"' in page.text
    assert 'id="composer-form"' in page.text

    script = client.get("/static/chat.js")
    styles = client.get("/static/chat.css")
    assert script.status_code == 200
    assert "Bearer ${state.token}" in script.text
    assert styles.status_code == 200
    assert "@media(max-width:700px)" in styles.text
