# POB Muster Checker Agent Guide

## Project purpose

POB Muster Checker compares people listed in the `POB` worksheet of an Excel
workbook with abbreviated names and cabin/bed identifiers read from muster-board
images by Google Gemini.

## Current architecture

- `index.html` is a framework-free single-page frontend containing the HTML,
  CSS, Excel import, image resizing, comparison logic, filtering, and rendering.
- `main.py` is a FastAPI application that serves `index.html`, accepts one image
  per OCR request, calls Gemini, and parses Gemini's text response.
- `vercel.json` routes both page and API traffic to the Vercel Python function.
- There is no database, persistent server state, Node build, or authentication.

## Responsibilities

### Frontend

- Load SheetJS from cdnjs and parse the worksheet named `POB` in the browser.
- Resize selected images to JPEG before upload.
- Send images to `/api/read-image`, with at most two requests in progress.
- Compare OCR records with Excel records using the existing matching rules.
- Render status summaries, filters, image counts, raw OCR, and manual overrides.

### Backend

- Serve the application page.
- Expose the minimal `/api/health` endpoint.
- Validate the image request and enforce the 4 MB limit.
- Call the configured Gemini model cascade and parse `CABIN_ID|NAME` lines.
- Never perform the Excel comparison or persist uploaded data.

## Local Windows commands

From PowerShell in the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m uvicorn main:app --reload
```

If the Python Launcher is installed, `py -m ...` may be used instead of
`python -m ...`.

Run tests with:

```powershell
python -m pytest -q
node tests/test_matching.js
```

## Secret handling

- Never commit a real `GEMINI_API_KEY` or paste it into tests, documentation,
  fixtures, logs, screenshots, or issue text.
- Use only obvious placeholders such as `test-placeholder-key` in tests.
- Keep local secrets in ignored `.env` or `.env.local` files or in the process
  environment.
- Tests must mock Gemini and must never make a real Gemini request.
- Health and error responses must not reveal secrets or configuration state.

## Branch and deployment safety

- Work only on the owner-approved branch and inspect `git status` before edits.
- Do not switch to or modify `main` unless the owner explicitly requests it.
- Do not commit, push, merge, deploy, or change Vercel settings without explicit
  owner approval for that action.
- Production deployment must never occur without owner approval.
- Preserve unrelated owner changes and avoid destructive Git commands.

## Accepted current behavior

- The Excel sheet must be named `POB` and uses columns A, B, C, D, and G.
- Parsing stops at `HOT BED`, `ONE DAY`, or a `SUMMARY` row.
- Exact section text maps marine and catering; other records map to passenger.
- Images are resized in the browser and scanned with the existing Gemini prompt
  and model cascade.
- OCR cabin forms such as `B401A` and `B-401A` normalize to `B-401A`.
- The frontend assigns each logical OCR tag to at most one POB record and
  classifies records as `ok`, `review`, or `absent` using deterministic rules
  documented in `MATCHING_SPEC.md`.
- `ok` requires exact cabin+bed and a unique exact name or safe surname
  abbreviation. Typos, ambiguity, and conflicting evidence require review.
- Identical POB records competing for one logical tag are never silently chosen.
- Manual status overrides and all other application state are browser-only and
  are lost on refresh.
- `/api/read-image` checks for the Gemini key before processing upload details.

Do not change these accepted behaviors, the Gemini prompt/model order, or the
Excel import rules without a separately approved change.
