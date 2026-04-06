import os
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

@app.get("/", response_class=HTMLResponse)
async def root():
    base_path = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_path, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/read-image")
async def read_image(files: List[UploadFile] = File(...)):
    try:
        # สั่งให้ AI กวาดข้อความบนป้ายมาทั้งหมด (ทั้งเลขห้องและชื่อ) บรรทัดละ 1 ป้าย
        instruction = """
        Read all the text on the muster board magnetic strips or cards.
        Return the text line by line exactly as you see it. 
        Include both Cabin Numbers and Names (e.g. '401A SURIYA' or '401 SURIYA').
        Do not format as JSON.
        """
        
        content_to_send = [instruction]
        for file in files:
            image_bytes = await file.read()
            content_to_send.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(content_to_send)
        
        # คืนค่ากลับไปเป็น List ของข้อความดิบๆ ที่ AI อ่านได้
        ai_lines = [line.strip().upper() for line in response.text.strip().split('\n') if len(line.strip()) > 1]
        
        return JSONResponse(content=ai_lines)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
