# Security Audit — Job Analyzer
**Date:** 2026-06-03  
**Branch:** redesign  
**Auditor:** Claude (claude-sonnet-4-6)  
**Scope:** Full codebase — `src/`, `static/`, `index.html`, `requirements.txt`  
**Deployment context:** Personal home-server tool, single user, localhost-only (`127.0.0.1:5003`)

---

## Executive Summary

The application demonstrates solid foundational security practices: parameterized SQL throughout, consistent HTML escaping in the frontend, no secrets committed to git, and no use of dangerous deserialization or code-execution functions. The main risks are concentrated in three areas that could drain Anthropic API credits or allow LAN-based resource abuse: no rate limiting, unbounded file uploads, and an SSRF-open URL parser. These are addressed in the remediation section below.

---

## STRIDE Threat Model

| Threat | Vector | Status |
|--------|--------|--------|
| **Spoofing** | No auth — acceptable for single-user localhost tool | Accepted (by design) |
| **Tampering** | Parameterized SQL, Pydantic model validation on all inputs | Mitigated |
| **Repudiation** | No audit log — `print()` to stdout only | Partially mitigated (see M3) |
| **Information Disclosure** | PII in `profile.json` and `job_analysis.db` — both gitignored, local-only | Accepted (local filesystem) |
| **Denial of Service** | No rate limiting; unbounded file upload size | **Not mitigated — fix required** |
| **Elevation of Privilege** | SSRF via user-supplied URL could reach LAN admin panels | **Not mitigated — fix required** |

---

## Findings

### HIGH — Action Required

---

#### H1 — No Rate Limiting on API-Triggering Endpoints

**Files:** [src/web.py](../src/web.py)  
**Endpoints:** `/api/analyze/{mode}`, `/api/search`, `/api/profile/upload-resume`

Every call to `/api/analyze` and `/api/search` invokes the Anthropic Claude API (paid per token). There is no rate limiting or request throttling. A runaway client loop or any device on the same LAN could exhaust API credits.

**Remediation:**
```python
# requirements.txt — add:
slowapi>=0.1.9

# src/web.py
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@limiter.limit("10/minute")
@app.post("/api/analyze/{mode}")
async def analyze_job(request: Request, mode: AnalyzeMode, ...):
    ...

@limiter.limit("10/minute")
@app.post("/api/search")
async def search_jobs(request: Request):
    ...

@limiter.limit("5/minute")
@app.post("/api/profile/upload-resume")
async def upload_resume(request: Request, file: UploadFile = File(...)):
    ...
```

---

#### H2 — PDF Upload: Extension-Only Validation, No Size Cap

**File:** [src/web.py:72–76](../src/web.py#L72)  
**Also:** [src/web.py:108–110](../src/web.py#L108)

PDF files are validated only by checking that the filename ends in `.pdf`. An attacker could:
- Upload a renamed non-PDF file that crashes `PdfReader`
- Upload a multi-gigabyte file to exhaust memory

**Remediation:**
```python
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

async def _read_pdf(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds 10 MB limit")
    if not content[:5].startswith(b"%PDF-"):
        raise HTTPException(400, "File is not a valid PDF")
    return content
```
Call `_read_pdf(file)` in both the resume upload and the PDF analyze branch instead of `await file.read()`.

---

#### H3 — SSRF: User-Supplied URLs Reach LAN Services

**File:** [src/parser.py:108–127](../src/parser.py#L108)

`parse_url()` accepts any URL string and fetches it with `requests` (and optionally Playwright). No scheme or IP validation is performed. A crafted URL can target:
- `http://192.168.x.x/` — home router admin panel
- `http://127.0.0.1:PORT/` — other local services
- `file://` / `gopher://` — alternative schemes

**Remediation:**
```python
import ipaddress, socket
from urllib.parse import urlparse

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise ValueError("Could not resolve hostname")
    for _, _, _, _, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(ip in net for net in _PRIVATE_NETS):
            raise ValueError(f"URL resolves to a private/internal address: {ip}")
```
Call `_validate_url(url)` at the top of `parse_url()`.

---

### MEDIUM — Worth Fixing

---

#### M1 — No Input Length Cap on `job_text`

**File:** [src/web.py:94](../src/web.py#L94)

The `job_text` form field has no size constraint. A multi-megabyte paste is forwarded to Claude (token cost) and held in memory.

**Remediation:** After receiving `job_text`, add:
```python
MAX_TEXT_LEN = 50_000
if job_text and len(job_text) > MAX_TEXT_LEN:
    raise HTTPException(400, f"Job text exceeds {MAX_TEXT_LEN:,} character limit")
```

---

#### M2 — `mode` Path Parameter Accepts Arbitrary Strings

**File:** [src/web.py:90–91](../src/web.py#L90)

`mode: str` allows any value. FastAPI will silently fall through to the `else` (text) branch for unknown modes, which can be confusing and hides bugs.

**Remediation:**
```python
from enum import Enum

class AnalyzeMode(str, Enum):
    url = "url"
    pdf = "pdf"
    text = "text"

@app.post("/api/analyze/{mode}")
async def analyze_job(mode: AnalyzeMode, ...):
```
FastAPI will automatically return a `422 Unprocessable Entity` for invalid mode values.

---

#### M3 — `print()` Used for All Error Reporting

**Files:** `src/web.py`, `src/analyzer.py`, `src/parser.py`

Errors are written to stdout via `print()`. This provides no log levels, no timestamps, no structured output, and makes debugging in production difficult.

**Remediation:** Replace with the standard `logging` module:
```python
import logging
logger = logging.getLogger(__name__)

# Replace: print(f"Resume Error: {e}")
# With:    logger.error("Resume upload failed: %s", e)
```
Add to `web.py` startup:
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)
```

---

#### M4 — Prompt Injection Risk (Informational)

**File:** [src/parser.py:143–168](../src/parser.py#L143)

Raw job-posting text is embedded directly in the Claude extraction prompt with no sanitization. A malicious job description could attempt to override the prompt instructions. For a personal tool this is low-impact (you control what URLs you submit), but worth noting.

**Recommendation:** No immediate action required for personal use. If the app is ever shared, add an instruction-injection guard or use Claude's system prompt to strongly anchor the task.

---

### LOW / INFO — Accepted or Not Actionable

| # | Finding | Disposition |
|---|---------|-------------|
| L1 | No CSRF protection | Accepted — no sessions/cookies in this architecture; not exploitable |
| L2 | No authentication | Accepted — single-user localhost by design |
| L3 | No HTTP security headers | Low value for localhost-only app; not actionable |
| L4 | `.env` never committed to git | **Good hygiene — no action needed** |
| L5 | `load_dotenv()` called in 4 modules | Harmless; `python-dotenv` ignores re-loads |

---

## Positive Findings

These were checked and confirmed **not vulnerable**:

| Area | Finding |
|------|---------|
| SQL Injection | All queries use `?` parameterization throughout [src/database.py](../src/database.py) |
| XSS | `_esc()` HTML-escapes all user/API data in [static/scripts.js:582–589](../static/scripts.js#L582); job card data set via `textContent` |
| Secrets in git | `.env` has **never** appeared in any commit (`git log -- .env` returns empty) |
| Deserialization | No `pickle`, `marshal`, or unsafe `yaml.load()` anywhere |
| Code execution | No `eval()`, `exec()`, `os.system()`, or `shell=True` anywhere |
| Dependency CVEs | All packages pinned to recent versions; no known critical CVEs in `requirements.txt` |

---

## Remediation Priority

| Priority | Finding | Effort |
|----------|---------|--------|
| 1 | H3 — SSRF protection | ~20 lines in `parser.py` |
| 2 | H2 — PDF magic bytes + size cap | ~10 lines in `web.py` |
| 3 | H1 — Rate limiting | Add `slowapi`, ~15 lines in `web.py` |
| 4 | M2 — AnalyzeMode enum | 5 lines |
| 5 | M1 — job_text length cap | 3 lines |
| 6 | M3 — Replace print with logging | Mechanical refactor |

---

## Verification Steps

After applying fixes, verify with:

1. **Rate limiting:** Rapid-fire 12 POST requests to `/api/analyze/text` → expect 429 on request 11+
2. **SSRF:** `POST /api/analyze/url` with `url=http://127.0.0.1:5003/api/profile` → expect 400 "private/internal address"
3. **PDF magic bytes:** Upload a `.txt` file renamed to `.pdf` → expect 400 "not a valid PDF"
4. **File size:** Upload a file >10 MB with `.pdf` extension → expect 400 "exceeds 10 MB"
5. **AnalyzeMode enum:** `POST /api/analyze/badmode` → expect 422 Unprocessable Entity
6. **Text length cap:** POST `job_text` of 60,000 characters → expect 400 "exceeds character limit"
