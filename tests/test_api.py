from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

import main


PLACEHOLDER_KEY = "test-placeholder-key"


class MockGoogleResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def gemini_payload(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def test_root_serves_application(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "POB MUSTER CHECKER" in response.text


def test_health_is_minimal_and_non_sensitive(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_gemini_api_key_keeps_existing_precedence(client, monkeypatch):
    monkeypatch.setattr(main, "GEMINI_API_KEY", "")

    response = client.post(
        "/api/read-image",
        files={"files": ("board.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "GEMINI_API_KEY is not configured on the server."
    }


def test_missing_upload_returns_consistent_error(client, monkeypatch):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)

    response = client.post("/api/read-image")

    assert response.status_code == 400
    assert response.json() == {"error": "No image file was uploaded."}


def test_empty_upload_returns_consistent_error(client, monkeypatch):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)

    response = client.post(
        "/api/read-image",
        files={"files": ("board.jpg", b"", "image/jpeg")},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "The uploaded image is empty."}


def test_oversized_upload_retains_four_mb_limit(client, monkeypatch):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)

    response = client.post(
        "/api/read-image",
        files={
            "files": (
                "board.jpg",
                b"x" * (main.MAX_IMAGE_BYTES + 1),
                "image/jpeg",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["error"].startswith("Image too large")


def test_unsupported_image_type_is_rejected(client, monkeypatch):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)

    response = client.post(
        "/api/read-image",
        files={"files": ("board.gif", b"GIF89a", "image/gif")},
    )

    assert response.status_code == 415
    assert response.json() == {
        "error": "Unsupported image type. Use JPEG, PNG, or WebP."
    }


def test_unexpected_errors_do_not_return_tracebacks(client, monkeypatch):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)
    monkeypatch.setattr(
        main.base64, "b64encode", lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    response = client.post(
        "/api/read-image",
        files={"files": ("board.jpg", b"mock-image", "image/jpeg")},
    )

    assert response.status_code == 500
    assert response.json() == {"error": "Unexpected server error."}
    assert "trace" not in response.json()


@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp"])
def test_supported_image_request_uses_mocked_gemini(
    client, monkeypatch, mime
):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)
    mocked_call = AsyncMock(return_value="B401A|AKARANET SA")
    monkeypatch.setattr(main, "call_google", mocked_call)

    response = client.post(
        "/api/read-image",
        files={"files": ("board.image", b"mock-image-bytes", mime)},
    )

    assert response.status_code == 200
    assert response.json()["parsed"][0]["cabin_bed"] == "B-401A"
    assert response.json()["model_used"] == main.MODELS[0]["label"]
    mocked_call.assert_awaited_once()


def test_empty_gemini_output_falls_through_all_models(
    client, monkeypatch
):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)
    mocked_post = AsyncMock(
        return_value=MockGoogleResponse(200, gemini_payload("   "))
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", mocked_post)

    response = client.post(
        "/api/read-image",
        files={"files": ("board.jpg", b"mock-image", "image/jpeg")},
    )

    assert response.status_code == 500
    assert response.json()["error"].startswith("All Google models failed")
    assert mocked_post.await_count == len(main.MODELS)


def test_gemini_fallback_uses_next_model_with_mocked_http_responses(
    client, monkeypatch
):
    monkeypatch.setattr(main, "GEMINI_API_KEY", PLACEHOLDER_KEY)
    mocked_post = AsyncMock(
        side_effect=[
            MockGoogleResponse(429, text="quota"),
            MockGoogleResponse(200, gemini_payload("B401A|AKARANET SA")),
        ]
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", mocked_post)

    response = client.post(
        "/api/read-image",
        files={"files": ("board.jpg", b"mock-image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["model_used"] == main.MODELS[1]["label"]
    assert response.json()["parsed"][0]["name_tag"] == "AKARANET SA"
    assert mocked_post.await_count == 2
