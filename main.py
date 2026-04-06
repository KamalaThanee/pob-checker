import os
import re
from google import genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    try:
        instruction = """
You are an OCR system reading yellow magnetic name tags on a muster board.

Each tag contains two white label strips side by side:
- LEFT strip: Cabin ID in format like "2 LR-1 B401A" or "2 LR-5 B422B"
- RIGHT strip: Person's name (abbreviated), like "AKARANET SA" or "NATTAWUT SI"

Your task: Extract EVERY tag you can see. Output one tag per line.

Output format (strict):
CABIN_ID|NAME

Rules:
- CABIN_ID: copy exactly as printed, e.g. "2 LR-1 B401A"
- NAME: copy exactly as printed, e.g. "AKARANET SA"
- Separator is the pipe character |
- One entry per line
- Do NOT include headers, summaries, board numbers, or any other text
- If a name is partially cut off, include what you can read

Example output:
2 LR-1 B401A|AKARANET SA
2 LR-1 B401B|NOPPHAKORN YI
2 LR-1 B401C|ADISAK PO
2 LR-5 B422B|NATTAWUT SI
"""

        contents = [instruction]
        for file in files:
            image_bytes = await file.read()
            contents.append({"mime_type": file.content_type, "data": image_bytes})

        response = model.generate_content(contents)
        raw_text = response.text.strip()

        # Parse each line into structured objects
        results = []
        for line in raw_text.split('\n'):
            line = line.strip()
            if '|' not in line:
                continue
            parts = line.split('|', 1)
            if len(parts) != 2:
                continue
            cabin_raw = parts[0].strip().upper()
            name_raw = parts[1].strip().upper()

            # Extract the B-number part from cabin tag
            # e.g. "2 LR-1 B401A" → cabin="B-401", bed="A"
            m = re.search(r'B[- ]?(\d+)([A-D])\b', cabin_raw)
            if m:
                cabin_num = m.group(1)   # e.g. "401"
                bed_letter = m.group(2)   # e.g. "A"
                cabin_id = f"B-{cabin_num}"  # e.g. "B-401"
                cabin_bed = f"{cabin_id}{bed_letter}"  # e.g. "B-401A"
            else:
                # Fallback: use raw text as-is
                cabin_id = cabin_raw
                bed_letter = ""
                cabin_bed = cabin_raw

            results.append({
                "raw": line,
                "cabin": cabin_id,        # "B-401"
                "bed": bed_letter,         # "A"
                "cabin_bed": cabin_bed,    # "B-401A"
                "name_tag": name_raw       # "AKARANET SA"
            })

        return JSONResponse(content={"parsed": results, "raw": raw_text})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
