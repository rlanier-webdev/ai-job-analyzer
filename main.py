#!/usr/bin/env python3
"""Job Analyzer - AI-powered job posting analysis."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.web:app", host="127.0.0.1", port=8000, reload=False)
