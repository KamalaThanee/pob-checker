import os
import re
import base64
import httpx
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
HTML_PATH       = Path(__file__).parent / "index.html"
MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 4 MB after client resize
GOOGLE_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
SUPPORTED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

_http_client: Optional[httpx.AsyncClient] = None
_html_cache: Optional[str] = None

# Google AI Studio — tried in order on quota/rate-limit errors
MODELS = [
    {
        "id": "gemini-3.1-flash-lite",
        "label": "Gemini 3.1 Flash Lite (Google AI Studio)",
    },
    {
        "id": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite (Google AI Studio)",
    },
    {
        "id": "gemini-3-flash-preview",
        "label": "Gemini 3 Flash Preview (Google AI Studio)",
    },
]

PROMPT = """You are an OCR system reading yellow magnetic name tags on a muster board.

Each tag has two white label strips:
- LEFT strip: Cabin ID, e.g. "2 LR-1 B401A" or "2 LR-5 B422B"
- RIGHT strip: Abbreviated name, e.g. "AKARANET SA" or "NATTAWUT SI"

Extract EVERY tag visible. Output one tag per line in this exact format:
CABIN_ID|NAME

Rules:
- Copy CABIN_ID exactly as printed
- Copy NAME exactly as printed
- Use pipe | as separator
- One line per tag
- Skip board section numbers (1,2,3...) and headers

Example output:
2 LR-1 B401A|AKARANET SA
2 LR-1 B401B|NOPPHAKORN YI
2 LR-5 B422B|NATTAWUT SI"""


def _google_url(model_id: str) -> str:
    return f"{GOOGLE_API_BASE}/{model_id}:generateContent"


def _client() -> httpx.AsyncClient:
    if _http_client is None:
        raise RuntimeError("HTTP client not initialized")
    return _http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client, _html_cache
    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
    _html_cache = HTML_PATH.read_text(encoding="utf-8")
    yield
    await _http_client.aclose()
    _http_client = None


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


async def call_google(model_id: str, api_key: str, image_b64: str, mime: str) -> str:
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": mime, "data": image_b64}}
            ]
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
    }
    resp = await _client().post(f"{_google_url(model_id)}?key={api_key}", json=payload)
    if resp.status_code in (429, 403, 503):
        raise QuotaError(f"Google quota/rate limit ({model_id}): {resp.status_code}")
    if resp.status_code != 200:
        raise RuntimeError(f"Google error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Google response: {str(data)[:200]}")
    if not text or not text.strip():
        raise QuotaError(f"Empty response from {model_id}")
    return text.strip()


class QuotaError(Exception):
    pass


def parse_ocr(raw_text: str) -> list:
    results = []
    for line in raw_text.split("\n"):
        line = line.strip()
        if "|" not in line:
            continue
        cabin_raw, _, name_raw = line.partition("|")
        cabin_raw = cabin_raw.strip().upper()
        name_raw  = name_raw.strip().upper()
        # D617B, D-617B, B401A, B-401A — use last match (cabin id is usually at end)
        matches = re.findall(r'([A-Z])-?(\d+)([A-D])\b', cabin_raw)
        if matches:
            letter, num, bed = matches[-1]
            cabin_id  = f"{letter}-{num}"
            cabin_bed = f"{cabin_id}{bed}"
        else:
            cabin_id, bed, cabin_bed = cabin_raw, "", cabin_raw
        results.append({"raw": line, "cabin": cabin_id, "bed": bed,
                        "cabin_bed": cabin_bed, "name_tag": name_raw})
    return results


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=_html_cache or HTML_PATH.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/read-image")
async def read_image(files: Optional[List[UploadFile]] = File(None)):
    try:
        if not GEMINI_API_KEY:
            return error_response(
                "GEMINI_API_KEY is not configured on the server.", 500
            )

        if not files or files[0] is None:
            return error_response("No image file was uploaded.", 400)

        upload = files[0]
        mime = upload.content_type or ""
        if mime not in SUPPORTED_IMAGE_TYPES:
            return error_response(
                "Unsupported image type. Use JPEG, PNG, or WebP.", 415
            )

        image_bytes = await upload.read()
        if not image_bytes:
            return error_response("The uploaded image is empty.", 400)

        if len(image_bytes) > MAX_IMAGE_BYTES:
            return error_response(
                f"Image too large ({len(image_bytes)} bytes). Max {MAX_IMAGE_BYTES}.",
                413,
            )

        b64  = base64.b64encode(image_bytes).decode("ascii")

        last_error = "No models available"
        for model in MODELS:
            try:
                raw = await call_google(model["id"], GEMINI_API_KEY, b64, mime)
                return JSONResponse(content={
                    "parsed": parse_ocr(raw),
                    "raw": raw,
                    "model_used": model["label"],
                })
            except QuotaError as e:
                last_error = str(e)
            except Exception as e:
                last_error = str(e)

        return error_response(
            f"All Google models failed. Last error: {last_error}", 500
        )

    except Exception:
        return error_response("Unexpected server error.", 500)
