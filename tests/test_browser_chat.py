"""Browser chat assets are served alongside the versioned API."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app


def test_chat_page_and_assets_are_served() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert 'id="auth-form"' in page.text
    assert 'id="composer-form"' in page.text
    assert 'class="app-shell logged-out"' in page.text
    assert "Log in to Simple RAG" in page.text
    assert "Company knowledge" in page.text
    assert "Log out" in page.text
    assert "Disconnect" not in page.text

    script = client.get("/static/chat.js")
    styles = client.get("/static/chat.css")
    assert script.status_code == 200
    assert "Bearer ${state.token}" in script.text
    assert styles.status_code == 200
    assert "@media(max-width:700px)" in styles.text
    assert ".app-shell.logged-out .sidebar" in styles.text


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_selected_chat_is_restored_before_sending_after_reload() -> None:
    script = Path(__file__).with_name("browser_chat_state.cjs")
    subprocess.run(["node", str(script)], check=True)
