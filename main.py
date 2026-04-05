import os
import json
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fuzzywuzzy import fuzz, process
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
async def read_image(files: List[UploadFile] = File(...), excel_names: str = Form("[]")):
    try:
        # เตรียมข้อมูลภาพทั้งหมดเพื่อส่งให้ Gemini ทีเดียว
        content_to_send = ["Read names from ALL these board images. Return ONLY a single JSON array: [{\"name\":\"NAME\"}]"]
        
        for file in files:
            image_bytes = await file.read()
            content_to_send.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(content_to_send)
        # ล้างเศษข้อความที่ไม่ใช่ JSON ออก
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        ai_data = json.loads(clean_json)
        
        excel_list = json.loads(excel_names)
        if excel_list:
            for item in ai_data:
                # ทำ Fuzzy Matching เพื่อซ่อมชื่อที่อ่านผิดเล็กน้อย
                match, score = process.extractOne(item["name"], excel_list, scorer=fuzz.token_sort_ratio)
                if score >= 80: 
                    item["name"] = match
                    
        return JSONResponse(content=ai_data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
