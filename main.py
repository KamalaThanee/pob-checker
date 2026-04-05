import os
import json
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fuzzywuzzy import fuzz, process

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

@app.get("/", response_class=HTMLResponse)
async def root():
    # แก้ไขให้หาไฟล์ index.html ในโฟลเดอร์ปัจจุบันให้เจอแน่นอน
    base_path = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_path, "index.html")
    
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return f"Error: index.html not found. Current path: {base_path}"

@app.post("/api/read-image")
async def read_image(
    file: UploadFile = File(...),
    mode: str = Form("muster"),
    excel_names: str = Form("[]")
):
    try:
        image_bytes = await file.read()
        prompt = "Read names from this offshore muster board. Return ONLY a JSON array of objects: [{\"cabin\":\"D-618\",\"bed\":\"A\",\"name\":\"NAME HERE\",\"zone\":\"1\"}]"
        
        response = model.generate_content([prompt, {"mime_type": file.content_type, "data": image_bytes}])
        raw_text = response.text.strip().replace("```json", "").replace("```", "")
        ai_data = json.loads(raw_text)

        excel_list = json.loads(excel_names)
        if excel_list:
            for item in ai_data:
                ai_name = item.get("name", "")
                if ai_name:
                    best_match, score = process.extractOne(ai_name, excel_list, scorer=fuzz.token_sort_ratio)
                    if score >= 80:
                        item["name"] = best_match
        return JSONResponse(content=ai_data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
