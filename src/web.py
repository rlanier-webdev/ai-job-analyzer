import os
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .analyzer import JobAnalyzer
from .parser import JobParser
from .profile import Profile, load_profile, ProfileManager, save_profile

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

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize Services
parser = JobParser()
analyzer = JobAnalyzer()
profile_manager = ProfileManager()

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

@app.get("/static/styles.css")
async def get_styles():
    """Serve the CSS file."""
    css_path = static_dir / "styles.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(status_code=404, detail="CSS file not found")

@app.get("/static/scripts.js")
async def get_scripts():
    """Serve the JavaScript file."""
    js_path = static_dir / "scripts.js"
    if js_path.exists():
        return FileResponse(js_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="JavaScript file not found")

@app.get("/", response_class=HTMLResponse)
async def home():
    # Helper to load your index.html file
    try:
        return Path("index.html").read_text()
    except:
        return "<h1>Job Analyzer</h1><p>Please ensure index.html exists.</p>"