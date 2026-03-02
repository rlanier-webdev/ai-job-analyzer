# Job Analyzer

An AI-powered web application that analyzes job postings against your professional profile to provide intelligent matching recommendations, skill gap analysis, and personalized interview tips.

## Features

- **Resume Auto-fill**: Upload a PDF resume to automatically extract and structure your profile data
- **Multi-input Job Analysis**: Analyze jobs via pasted text, PDF upload, or URL scraping
- **Qualification Scoring**: Get a 0-100 match score with color-coded ratings
- **Skills Analysis**: See matching skills (green) vs. missing skills (red)
- **Apply Verdict**: Clear YES/NO recommendation with reasoning
- **Salary Assessment**: Compare job compensation against your expectations
- **Red/Green Flags**: Identify potential concerns and positive indicators
- **Interview Tips**: Personalized preparation advice based on the job requirements

## Tech Stack

- **Backend**: FastAPI, Uvicorn, Pydantic
- **AI**: Claude
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Data Processing**: BeautifulSoup4, pypdf

## Prerequisites

- Python 3.7+
- Claude API key

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/rlanier-webdev/ai-job-analyzer.git
   cd ai-job-analyzer
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

5. Add your Claude API key to `.env`:
   ```
   ANTHROPIC_API_KEY=your-api-key-here
   ```

## Usage

1. Start the server:
   ```bash
   python main.py
   ```

2. Open your browser to `http://127.0.0.1:8000`

3. Set up your profile:
   - Click "Auto-fill from Resume (PDF)" to upload your resume, OR
   - Click "Edit Manually" to enter your information

4. Analyze a job posting:
   - Choose input method (Paste Text / Upload PDF / Enter URL)
   - Provide the job posting content
   - Click "Analyze Job"

5. Review your results including qualification score, skill matches, and recommendations

## Project Structure

```
job-analyzer/
├── main.py              # Entry point - starts Uvicorn server
├── index.html           # Single-page application UI
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── profile.example.json # Sample profile structure
├── src/
│   ├── web.py          # FastAPI routes & endpoints
│   ├── parser.py       # Job posting extraction logic
│   ├── analyzer.py     # Job-profile matching analysis
│   └── profile.py      # Profile data model & management
└── static/
    ├── styles.css      # UI styling
    └── scripts.js      # Frontend JavaScript
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serve the web application |
| GET | `/api/profile` | Get current profile |
| POST | `/api/profile` | Save profile manually |
| POST | `/api/profile/upload-resume` | Parse resume PDF and create profile |
| POST | `/api/analyze/{mode}` | Analyze job (mode: text, pdf, or url) |

## Configuration

- **Profile Storage**: Your profile is saved to `profile.json` and automatically loaded on startup
- **Server**: Runs on `127.0.0.1:8000` (localhost only)

## Screenshots
<img width="945" height="811" alt="image" src="https://github.com/user-attachments/assets/7dc1bb3f-654c-4a86-98cd-56f98a237c26" />

## License

MIT
