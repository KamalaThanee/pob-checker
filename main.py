import os
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ใช้ Gemini 2.0 Flash ที่เร็วและแม่นยำที่สุด
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
        # ปรับ Prompt ให้เข้มงวดขึ้น เพื่อให้ Matching Engine ทำงานง่าย
        instruction = """
        TASK: Extract all name tags from the Muster Board.
        FORMAT: Output only [CabinID][Name] per line.
        EXAMPLE: 
        422ACHERDCHAI
        D618SURIYA
        RULES:
        - No spaces between CabinID and Name if possible.
        - No headers, no introductory text, no explanations.
        - If text is unclear, provide your best guess.
        """
        
        contents = [instruction]
        for file in files:
            image_bytes = await file.read()
            contents.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(contents)
        
        # กรองข้อมูลและทำความสะอาดเบื้องต้น
        lines = [line.strip().upper().replace(" ", "") for line in response.text.split('\n') if len(line.strip()) > 3]
        
        return JSONResponse(content=lines)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
