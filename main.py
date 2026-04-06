import os
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ใช้ Gemini 2.0 Flash เพื่อความเร็วและความฉลาดในการอ่านป้ายชื่อ
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
        # Prompt ใหม่: สั่งให้ AI สนใจแค่ข้อความบนป้ายแม่เหล็กเท่านั้น
        instruction = """
        OCR MODE: Extract all text from the magnetic name tags on the board.
        Output format: [CabinID][Name]
        Example: 422ACHERDCHAI
        Important: Ignore headers and summary tables at the bottom. 
        Just list the names from the tags. One per line.
        """
        
        contents = [instruction]
        for file in files:
            image_bytes = await file.read()
            contents.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(contents)
        
        # ส่งกลับไปเป็น List ของบรรทัดที่ AI อ่านได้ (ลบช่องว่างเพื่อความแม่นยำในการ Match)
        lines = [line.strip().upper().replace(" ", "") for line in response.text.split('\n') if len(line.strip()) > 3]
        return JSONResponse(content=lines)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
