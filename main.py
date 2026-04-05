import os
import json
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, Form
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
    base_path = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_path, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/read-image")
async def read_image(file: UploadFile = File(...), excel_names: str = Form("[]")):
    try:
        image_bytes = await file.read()
        prompt = "Read names from this board. Return ONLY JSON: [{\"name\":\"NAME\"}]"
        response = model.generate_content([prompt, {"mime_type": file.content_type, "data": image_bytes}])
        ai_data = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
        
        excel_list = json.loads(excel_names)
        if excel_list:
            for item in ai_data:
                match, score = process.extractOne(item["name"], excel_list, scorer=fuzz.token_sort_ratio)
                if score >= 80: item["name"] = match
        return JSONResponse(content=ai_data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})
