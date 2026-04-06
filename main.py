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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.0-flash-001"  # หรือจะเปลี่ยนเป็น model อื่นได้

HTML_PATH = Path(__file__).parent / "index.html"

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=HTML_PATH.read_text(encoding="utf-8"))

@app.get("/api/test-key")
async def test_key():
    if not OPENROUTER_API_KEY:
        return {"status": "ERROR", "reason": "OPENROUTER_API_KEY is empty"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "say hello"}],
                "max_tokens": 10
            }
        )
    return {"status": resp.status_code, "body": resp.json()}

@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    if not OPENROUTER_API_KEY:
        return JSONResponse(status_code=500, content={"error": "OPENROUTER_API_KEY not set"})

    try:
        prompt = """You are an OCR system reading yellow magnetic name tags on a muster board.

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

        # Build content parts (text + images)
        content_parts = [{"type": "text", "text": prompt}]

        for file in files:
            image_bytes = await file.read()
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            mime = file.content_type or "image/jpeg"
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}"
                }
            })

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "user", "content": content_parts}
            ],
            "max_tokens": 2048,
            "temperature": 0.1
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload
            )

        if resp.status_code != 200:
            return JSONResponse(
                status_code=500,
                content={"error": f"OpenRouter error {resp.status_code}: {resp.text[:500]}"}
            )

        raw_text = resp.json()["choices"][0]["message"]["content"].strip()

        results = []
        for line in raw_text.split("\n"):
            line = line.strip()
            if "|" not in line:
                continue
            cabin_raw, _, name_raw = line.partition("|")
            cabin_raw = cabin_raw.strip().upper()
            name_raw = name_raw.strip().upper()

            m = re.search(r'B-?(\d+)([A-D])\b', cabin_raw)
            if m:
                cabin_id = f"B-{m.group(1)}"
                bed_letter = m.group(2)
                cabin_bed = f"{cabin_id}{bed_letter}"
            else:
                cabin_id, bed_letter, cabin_bed = cabin_raw, "", cabin_raw

            results.append({
                "raw": line,
                "cabin": cabin_id,
                "bed": bed_letter,
                "cabin_bed": cabin_bed,
                "name_tag": name_raw
            })

        return JSONResponse(content={"parsed": results, "raw": raw_text})

    except Exception as e:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "trace": traceback.format_exc()}
        )
