## Commands

```
venv\Scripts\activate                        # activate virtual environment
uvicorn src.web:app --reload --port 8001     # start dev server
```

App runs at http://127.0.0.1:8001

## Project Structure

- `index.html` — single-page frontend (served from project root)
- `static/styles.css`, `static/scripts.js` — frontend assets
- `src/web.py` — FastAPI routes and app entry point
- `src/analyzer.py` — Claude-powered job analysis
- `src/parser.py` — job posting extraction (URL/PDF/text)
- `src/searcher.py` — Remotive API job search
- `src/profile.py` — profile data model and file persistence
- `profile.json` — persisted user profile (gitignored)

## Architecture

Pure frontend redesign on the `redesign` branch. Three-view SPA:
- **Profile** — inline profile form, resume auto-fill
- **Job Search** — find and score remote jobs via Remotive API
- **Analyze Job** — paste/upload/URL → AI report with score ring, skill chips, salary bar

Backend APIs are unchanged — all routes in `src/web.py`.

## Notes

- No `app/` directory — `uvicorn app.main:app` is incorrect for this project
- venv is `venv/` not `.venv/`
- Server binds to `127.0.0.1` (localhost only), port `8001`
