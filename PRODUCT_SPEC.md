# POB Muster Checker Product Specification

## Purpose

The application helps an operator compare the current POB Excel list with
yellow magnetic name tags visible in muster-board photographs. It identifies
records that match, records that need review, and people not found in the
photographs.

## Inputs

### Excel workbook

- The accepted file type is `.xlsx`.
- The workbook must contain a worksheet named `POB`.
- Column A contains a numeric row/person identifier.
- Column B contains the cabin.
- Column C contains the bed letter.
- Column D contains the name.
- Column G contains the section.
- Rows missing required A-D values are skipped.
- Header-like names `NAME`, `BARGE CREW`, `CATERING`, `PASSENGER`, and `SECTION`
  are skipped.
- Import stops when column D contains `HOT BED` or `ONE DAY`, or column A equals
  `SUMMARY`.

Section mapping is exact: `MARINE CREW` maps to marine, `CATERING CREW` maps to
catering, and every other accepted row maps to passenger/operation.

### Muster-board images

- The browser accepts multiple image selections.
- Before upload, each image is rendered to a canvas at no more than 1500 pixels
  wide and encoded as JPEG at 85 percent quality.
- The frontend processes at most two image requests concurrently.
- The backend accepts JPEG, PNG, and WebP request MIME types and enforces a 4 MB
  limit per uploaded image.

## OCR behavior

The backend sends one image and the existing muster-board prompt to Google
Gemini. It tries these models in order:

1. `gemini-3.1-flash-lite`
2. `gemini-2.5-flash-lite`
3. `gemini-3-flash-preview`

Gemini is instructed to produce one `CABIN_ID|NAME` record per line. Lines
without a pipe are ignored. Cabin and name text are uppercased. The last cabin
pattern consisting of a letter, digits, and bed A-D is normalized so, for
example, `B401A` and `B-401A` both become `B-401A`.

The backend returns parsed records, raw OCR text, and the label of the model
that succeeded. Empty model output and model errors advance to the next model.

## Comparison behavior

All comparison logic runs in the browser.

- `ok`: normalized cabin+bed matches and the name meets the existing similarity
  threshold.
- `review`: the name matches an OCR record but its cabin or bed differs.
- `absent`: no acceptable name match is found. If the expected bed contains a
  different OCR name, the explanation includes that occupant.

Name matching uses the existing first-name and surname equality/prefix rules.
OCR records are not consumed after a match, and the behavior is not guaranteed
to be one-to-one.

## Results and controls

- Totals are shown for matching, review, and absent statuses.
- Section totals are shown for marine, catering, and passenger/operation.
- Operators can filter by status, section, cabin/bed, and name.
- Per-image tag counts and raw OCR text are available in expandable sections.
- An operator can temporarily override a person to found or absent and can
  restore the automatic result.
- Overrides, imported data, and results are not persisted or exported.

## API behavior

- `GET /` serves the single-page application.
- `GET /api/health` returns `{"status":"ok"}` and no configuration details.
- `POST /api/read-image` requires the server's `GEMINI_API_KEY` and one supported
  image upload under the configured limit.
- Application-generated API failures return JSON containing an `error` field.

## Deployment

Vercel builds `main.py` with `@vercel/python` and routes both `/api/*` and all
other paths to the FastAPI application. Production requires the
`GEMINI_API_KEY` environment variable. Deployment is an owner-controlled action
and is not performed as part of local development or testing.
