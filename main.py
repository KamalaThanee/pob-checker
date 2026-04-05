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
# ใช้ Model Flash 1.5 เพราะอ่านตัวอักษรจากภาพได้แม่นที่สุด
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
        # ปรับคำสั่งให้ AI โฟกัสที่ชื่อภาษาอังกฤษบนบอร์ด Muster
        instruction = """
        Extract ALL English names from these Muster Board images. 
        - Look for names on the magnetic strips or labels.
        - Ignore headers, titles, or numbers.
        - Return ONLY a JSON array of objects: [{"name": "FULL NAME"}]
        - If no names found, return [].
        """
        
        content_to_send = [instruction]
        for file in files:
            image_bytes = await file.read()
            content_to_send.append({"mime_type": file.content_type, "data": image_bytes})
        
        response = model.generate_content(content_to_send)
        clean_json = response.text.strip().replace("```json", "").replace("```", "")
        ai_data = json.loads(clean_json)
        
        excel_list = json.loads(excel_names)
        results = []

        if excel_list:
            for item in ai_data:
                raw_name = str(item["name"]).upper().strip()
                # ใช้ Fuzzy Matching เพื่อเทียบชื่อที่ AI อ่านเพี้ยน กับชื่อจริงใน Excel
                match, score = process.extractOne(raw_name, excel_list, scorer=fuzz.token_sort_ratio)
                if score >= 70: # ปรับความยืดหยุ่นลงเหลือ 70 เพื่อให้ดึงข้อมูลง่ายขึ้น
                    results.append({"name": match})
                else:
                    results.append({"name": raw_name}) # ถ้าไม่เจอใน Excel ให้เอาชื่อดิบที่อ่านได้มาแสดง
                    
        return JSONResponse(content=results)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
