import os
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ตรวจสอบว่าใช้ Gemini 2.0 Flash เพื่อความเร็ว
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
        # Prompt ที่บังคับให้ AI โฟกัสแค่ตัวอักษรบนป้ายชื่อเท่านั้น
        instruction = "Extract all [Cabin][Name] from the name tags. Format: 'CabinName' (e.g. 422ACHERDCHAI). One per line. No intro."
        
        contents = [instruction]
        for file in files:
            image_bytes = await file.read()
            contents.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(contents)
        # ล้างช่องว่างและทำให้เป็นตัวพิมพ์ใหญ่ทั้งหมด
        lines = [line.strip().upper().replace(" ", "") for line in response.text.split('\n') if len(line.strip()) > 3]
        return JSONResponse(content=lines)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
