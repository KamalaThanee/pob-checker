import os
import re
import base64
import httpx
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
HTML_PATH          = Path(__file__).parent / "index.html"

# ---- Model cascade (tried in order) ----
MODELS = [
    {
        "id": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash (Google Free)",
        "provider": "google",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    },
    {
        "id": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite (Google Free)",
        "provider": "google",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
    },
    {
        "id": "nvidia/nemotron-nano-12b-v2-vl:free",
        "label": "Nemotron 12B VL (OpenRouter Free)",
        "provider": "openrouter",
    },
    {
        "id": "google/gemma-4-31b-it:free",
        "label": "Gemma 4 31B (OpenRouter Free)",
        "provider": "openrouter",
    },
    {
        "id": "google/gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite (OpenRouter Paid)",
        "provider": "openrouter",
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


async def call_google(url: str, api_key: str, image_b64: str, mime: str) -> str:
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": mime, "data": image_b64}}
            ]
        }],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{url}?key={api_key}", json=payload)
    if resp.status_code == 429 or resp.status_code == 403:
        raise QuotaError(f"Google quota: {resp.status_code}")
    if resp.status_code != 200:
        raise RuntimeError(f"Google error {resp.status_code}: {resp.text[:200]}")
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


async def call_openrouter(model_id: str, api_key: str, image_b64: str, mime: str) -> str:
    payload = {
        "model": model_id,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}}
            ]
        }],
        "max_tokens": 2048,
        "temperature": 0.1
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload
        )
    if resp.status_code == 429 or resp.status_code == 402:
        raise QuotaError(f"OpenRouter quota/payment: {resp.status_code}")
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    # Some free models return empty content when overloaded
    content = data["choices"][0]["message"].get("content") or ""
    if not content.strip():
        raise QuotaError("Empty response (model overloaded)")
    return content.strip()


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
    return HTMLResponse(content=HTML_PATH.read_text(encoding="utf-8"))


@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    try:
        image_bytes = await files[0].read()
        b64  = base64.b64encode(image_bytes).decode("utf-8")
        mime = files[0].content_type or "image/jpeg"

        last_error = "No API keys configured"
        for model in MODELS:
            # Skip if required key is missing
            if model["provider"] == "google" and not GEMINI_API_KEY:
                continue
            if model["provider"] == "openrouter" and not OPENROUTER_API_KEY:
                continue

            try:
                if model["provider"] == "google":
                    raw = await call_google(model["url"], GEMINI_API_KEY, b64, mime)
                else:
                    raw = await call_openrouter(model["id"], OPENROUTER_API_KEY, b64, mime)

                parsed = parse_ocr(raw)
                return JSONResponse(content={
                    "parsed": parsed,
                    "raw": raw,
                    "model_used": model["label"]
                })

            except QuotaError as e:
                last_error = str(e)
                continue  # Try next model
            except Exception as e:
                last_error = str(e)
                continue  # Try next model

        return JSONResponse(status_code=500, content={"error": f"All models failed. Last error: {last_error}"})

    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})
