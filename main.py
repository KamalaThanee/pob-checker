import os
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# เปลี่ยนมาใช้ Gemini 2.0 Flash ตามที่คุณแนะนำ (เร็วกว่าและแม่นกว่ามาก)
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
        # Prompt แบบสั้นพิเศษเพื่อลดการค้างและเพิ่มความเร็ว
        instruction = "List all [CabinID][Name] from the name tags. One per line. Example: 422A CHERDCHAI"
        
        contents = [instruction]
        for file in files:
            image_bytes = await file.read()
            contents.append({"mime_type": file.content_type, "data": image_bytes})
        
        # ส่งข้อมูลไปประมวลผล
        response = model.generate_content(contents)
        # กรองเฉพาะบรรทัดที่มีข้อมูลจริงๆ
        lines = [line.strip().upper() for line in response.text.split('\n') if len(line.strip()) > 3]
        
        return JSONResponse(content=lines)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
