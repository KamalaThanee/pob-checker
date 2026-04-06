import os
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ตั้งค่า Gemini
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    try:
        # สั่ง AI ให้อ่านข้อมูลดิบจากป้ายชื่อ
        instruction = """
        Extract all text from the magnetic name strips on this Muster Board. 
        Focus on Cabin ID (e.g. 422A, D-618) and Name.
        Return the result line by line. 
        Format: [CabinID] [Name]
        Example: 
        422A CHERDCHAI
        D-618 SURIYA
        """
        
        contents = [instruction]
        for file in files:
            image_bytes = await file.read()
            contents.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(contents)
        # ส่งค่ากลับเป็น List ของข้อความที่อ่านได้
        lines = [l.strip().upper() for l in response.text.split('\n') if len(l.strip()) > 2]
        return JSONResponse(content=lines)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
