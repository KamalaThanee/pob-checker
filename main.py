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
        m = re.search(r'B-?(\d+)([A-D])\b', cabin_raw)
        if m:
            cabin_id  = f"B-{m.group(1)}"
            bed       = m.group(2)
            cabin_bed = f"{cabin_id}{bed}"
        else:
            cabin_id, bed, cabin_bed = cabin_raw, "", cabin_raw
        results.append({"raw": line, "cabin": cabin_id, "bed": bed,
                        "cabin_bed": cabin_bed, "name_tag": name_raw})
    return results


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=_html_cache or HTML_PATH.read_text(encoding="utf-8"))


@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    try:
        if not GEMINI_API_KEY:
            return JSONResponse(
                status_code=500,
                content={"error": "GEMINI_API_KEY is not configured on the server."},
            )

        image_bytes = await files[0].read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": f"Image too large ({len(image_bytes)} bytes). Max {MAX_IMAGE_BYTES}."},
            )

        b64  = base64.b64encode(image_bytes).decode("ascii")
        mime = files[0].content_type or "image/jpeg"

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

        return JSONResponse(
            status_code=500,
            content={"error": f"All Google models failed. Last error: {last_error}"},
        )

    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})
