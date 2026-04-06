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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

HTML_PATH = Path(__file__).parent / "index.html"

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=HTML_PATH.read_text(encoding="utf-8"))

@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    if not GEMINI_API_KEY:
        return JSONResponse(status_code=500, content={"error": "GEMINI_API_KEY not set"})

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

        parts = [{"text": prompt}]
        for file in files:
            image_bytes = await file.read()
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            parts.append({"inline_data": {"mime_type": file.content_type or "image/jpeg", "data": b64}})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload)

        if resp.status_code != 200:
            return JSONResponse(status_code=500, content={"error": f"Gemini error {resp.status_code}: {resp.text[:300]}"})

        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

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
            results.append({"raw": line, "cabin": cabin_id, "bed": bed_letter, "cabin_bed": cabin_bed, "name_tag": name_raw})

        return JSONResponse(content={"parsed": results, "raw": raw_text})

    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})

@app.get("/api/test-key")
async def test_key():
    import httpx
    if not GEMINI_API_KEY:
        return {"status": "ERROR", "reason": "GEMINI_API_KEY is empty"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": "say hello"}]}]}
        )
    return {"status": resp.status_code, "body": resp.json()}
