# POB Muster Checker

เว็บตรวจเช็กรายชื่อบน muster board โดยอ่านป้ายชื่อจากรูปด้วย Gemini (Google AI Studio) แล้วเทียบกับไฟล์ Excel

**Live:** [pob-checker.vercel.app](https://pob-checker.vercel.app/)

## Model cascade (Google AI Studio)

ลำดับเมื่อโดน rate limit / quota:

1. `gemini-3.1-flash-lite`
2. `gemini-2.5-flash-lite`
3. `gemini-3-flash-preview`

## Deploy บน Vercel

1. Repo: [github.com/KamalaThanee/pob-checker](https://github.com/KamalaThanee/pob-checker)
2. ตั้ง **Environment Variable**: `GEMINI_API_KEY` จาก [Google AI Studio](https://aistudio.google.com/apikey)
3. ลบ `OPENROUTER_API_KEY` ออกจาก Vercel ได้ (ไม่ใช้แล้ว)

## รันบนเครื่อง

```bash
pip install -r requirements.txt
set GEMINI_API_KEY=your_key
uvicorn main:app --reload
```
