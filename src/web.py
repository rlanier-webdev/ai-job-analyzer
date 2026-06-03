import logging
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

from .analyzer import JobAnalyzer
from .database import init_db, save_analysis, list_analysis, get_analysis
from .parser import JobParser, JobPosting
from .profile import Profile, load_profile, ProfileManager, save_profile
from .searcher import JobSearcher

# Load .env at the very start
load_dotenv()

PROFILE_PATH = Path(__file__).parent.parent / "profile.json"
DB_PATH = Path(__file__).parent.parent / "job_analysis.db"
global_data = {"profile": None, "db": None}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown. 
    Checks for API keys and loads the local profile if it exists.
    """
    # Startup Logic
    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY is missing from .env")

    global_data["db"] = init_db(DB_PATH)
    logger.info("Database ready")

    if PROFILE_PATH.exists():
        try:
            global_data["profile"] = load_profile(PROFILE_PATH)
            logger.info("Profile loaded from profile.json")
        except Exception as e:
            logger.warning("Could not load profile: %s", e)
    
    yield
    # Shutdown logic (if any) goes here

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Job Analyzer",
    description="Intelligent job matching with Claude",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=500)

_executor = ThreadPoolExecutor(max_workers=10)

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize Services
parser = JobParser()
analyzer = JobAnalyzer()
profile_manager = ProfileManager()
searcher = JobSearcher()

class AnalyzeMode(str, Enum):
    url = "url"
    pdf = "pdf"
    text = "text"


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


async def _read_validated_pdf(file: UploadFile) -> bytes:
    """Read an uploaded file and reject if it exceeds the size limit or lacks a PDF magic header."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10 MB size limit")
    if not content[:5].startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="File is not a valid PDF")
    return content


# --- API ENDPOINTS ---

@app.post("/api/profile/upload-resume")
@limiter.limit("5/minute")
async def upload_resume(request: Request, file: UploadFile = File(...)):
    """Automatically creates a profile from a resume PDF."""
    try:
        content = await _read_validated_pdf(file)
        # 1. Extract text from PDF
        job_data = parser.parse_pdf(content)
        # 2. Structure the profile
        new_profile = profile_manager.create_profile_from_resume(job_data.raw_text)
        # 3. Update global state and save
        global_data["profile"] = new_profile
        save_profile(new_profile, PROFILE_PATH)
        
        return new_profile.model_dump()
    except Exception as e:
        logger.error("Resume upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")

@app.post("/api/analyze/{mode}")
@limiter.limit("10/minute")
async def analyze_job(
    request: Request,
    mode: AnalyzeMode,
    url: str = Form(None),
    job_text: str = Form(None),
    file: UploadFile = File(None),
):
    """Unified analysis for URL, Text, or PDF."""
    current_profile = global_data.get("profile")
    if not current_profile:
        raise HTTPException(status_code=400, detail="Please upload or create a profile first.")

    try:
        # 1. Parse job based on mode
        if mode == AnalyzeMode.url:
            if not url: raise HTTPException(400, "URL required")
            job = await parser.parse_url(url)
        elif mode == AnalyzeMode.pdf:
            if not file: raise HTTPException(400, "PDF file required")
            content = await _read_validated_pdf(file)
            job = parser.parse_pdf(content)
        else:
            if not job_text: raise HTTPException(400, "Job text required")
            if len(job_text) > 50_000:
                raise HTTPException(400, "Job text exceeds the 50,000 character limit")
            job = parser.parse_text(job_text)

        # 2. Run Analysis
        result = analyzer.analyze(job, current_profile)
        
        # 3. Save to history and return combined data for the UI
        response_data = {
            **result.model_dump(),
            "job_title": job.title,
            "job_company": job.company,
            "job_location": job.location,
            "salary_range": job.salary_range,
            "job_type": job.job_type,
            "remote_policy": job.remote_policy,
            "source_url": job.source_url,
        }
        row_id = save_analysis(global_data["db"], response_data)
        return {**response_data, "id": row_id}
    except Exception as e:
        logger.error("Analysis failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
@limiter.limit("10/minute")
async def search_jobs(request: Request):
    """Search Remotive for jobs matching the loaded profile; auto-analyze top 5."""
    current_profile = global_data.get("profile")
    if not current_profile:
        raise HTTPException(status_code=400, detail="Please upload or create a profile first.")

    semaphore = asyncio.Semaphore(3)

    async def _analyze_one(result):
        job_posting = JobPosting(
            title=result.title,
            company=result.company,
            location=result.location,
            salary_range=result.salary,
            job_type="full-time",
            remote_policy=result.remote_policy,
            description=result.description_snippet,
            requirements=result.tags,
            nice_to_have=[],
            benefits=[],
            source_url=result.url,
        )
        loop = asyncio.get_running_loop()
        async with semaphore:
            analysis = await loop.run_in_executor(_executor, analyzer.analyze, job_posting, current_profile)
        return result, analysis

    try:
        results = searcher.search(current_profile, limit=10)
        query_used = searcher.build_query(current_profile)

        pairs = await asyncio.gather(*[_analyze_one(r) for r in results])
        jobs = [
            {
                **r.model_dump(),
                "score": a.qualification_score,
                "should_apply": a.should_apply,
                "summary": a.qualification_summary,
            }
            for r, a in pairs if a.qualification_score >= 75
        ]
        jobs.sort(key=lambda j: j["score"], reverse=True)
        return {"jobs": jobs, "query_used": query_used}
    except Exception as e:
        logger.error("Search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/profile")
async def save_profile_endpoint(profile: Profile):
    """Save a manually created profile."""
    try:
        # Update global state and save to disk
        global_data["profile"] = profile
        save_profile(profile, PROFILE_PATH)
        return profile.model_dump()
    except Exception as e:
        logger.error("Profile save failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")

@app.get("/api/profile")
async def get_profile():
    """Return the current profile."""
    current_profile = global_data.get("profile")
    if not current_profile:
        raise HTTPException(status_code=404, detail="No profile loaded")
    return current_profile.model_dump()

@app.get("/api/history")
async def get_history():
    return list_analysis(global_data["db"])


@app.get("/api/history/{analysis_id}")
async def get_history_entry(analysis_id: int):
    entry = get_analysis(global_data["db"], analysis_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return entry


@app.get("/", response_class=HTMLResponse)
async def home():
    # Helper to load your index.html file
    return (Path(__file__).parent.parent / "index.html").read_text(encoding="utf-8")