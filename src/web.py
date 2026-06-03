import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .analyzer import JobAnalyzer
from .parser import JobParser, JobPosting
from .profile import Profile, load_profile, ProfileManager, save_profile
from .searcher import JobSearcher

# Load .env at the very start
load_dotenv()

PROFILE_PATH = Path(__file__).parent.parent / "profile.json"
global_data = {"profile": None}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown. 
    Checks for API keys and loads the local profile if it exists.
    """
    # Startup Logic
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ERROR: ANTHROPIC_API_KEY is missing from .env!")
    
    if PROFILE_PATH.exists():
        try:
            global_data["profile"] = load_profile(PROFILE_PATH)
            print("✅ Profile loaded from profile.json")
        except Exception as e:
            print(f"⚠️ Could not load profile: {e}")
    
    yield
    # Shutdown logic (if any) goes here

app = FastAPI(
    title="Job Analyzer",
    description="Intelligent job matching with Claude",
    lifespan=lifespan
)
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

# --- API ENDPOINTS ---

@app.post("/api/profile/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """Automatically creates a profile from a resume PDF."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF resume")
    
    try:
        content = await file.read()
        # 1. Extract text from PDF
        job_data = parser.parse_pdf(content)
        # 2. Structure the profile
        new_profile = profile_manager.create_profile_from_resume(job_data.raw_text)
        # 3. Update global state and save
        global_data["profile"] = new_profile
        save_profile(new_profile, PROFILE_PATH)
        
        return new_profile.model_dump()
    except Exception as e:
        print(f"Resume Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {str(e)}")

@app.post("/api/analyze/{mode}")
async def analyze_job(
    mode: str, 
    url: str = Form(None), 
    job_text: str = Form(None), 
    file: UploadFile = File(None)
):
    """Unified analysis for URL, Text, or PDF."""
    current_profile = global_data.get("profile")
    if not current_profile:
        raise HTTPException(status_code=400, detail="Please upload or create a profile first.")

    try:
        # 1. Parse job based on mode
        if mode == "url":
            if not url: raise HTTPException(400, "URL required")
            job = await parser.parse_url(url)
        elif mode == "pdf":
            if not file: raise HTTPException(400, "PDF file required")
            content = await file.read()
            job = parser.parse_pdf(content)
        else:
            if not job_text: raise HTTPException(400, "Job text required")
            job = parser.parse_text(job_text)

        # 2. Run Analysis
        result = analyzer.analyze(job, current_profile)
        
        # 3. Return combined data for the UI
        return {
            **result.model_dump(), 
            "job_title": job.title, 
            "job_company": job.company
        }
    except Exception as e:
        print(f"Analysis Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search_jobs():
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
        print(f"Search Error: {e}")
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
        print(f"Profile Save Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save profile: {str(e)}")

@app.get("/api/profile")
async def get_profile():
    """Return the current profile."""
    current_profile = global_data.get("profile")
    if not current_profile:
        raise HTTPException(status_code=404, detail="No profile loaded")
    return current_profile.model_dump()

@app.get("/", response_class=HTMLResponse)
async def home():
    # Helper to load your index.html file
    try:
        return Path("index.html").read_text()
    except:
        return "<h1>Job Analyzer</h1><p>Please ensure index.html exists.</p>"