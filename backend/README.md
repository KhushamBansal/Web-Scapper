# Backend - Technical Content Scraper

## Overview
This backend provides API endpoints for scraping technical content from blogs, guides, and PDFs. It now includes a Scrapy-based crawler with Gemini AI integration for smart link filtering.

## Key Features
- FastAPI API endpoints for scraping single URLs, bulk scraping, PDF extraction, and knowledge base management
- Scrapy-based high-performance crawling with Gemini AI link filtering
- MongoDB for storage

## Scrapy Gemini Integration
- The Scrapy spider is in `gemini_crawler/gemini_crawler/spiders/gemini_spider.py`.
- The `/api/scrapy-crawl` endpoint runs the spider as a subprocess and returns results to the frontend.
- Gemini AI is used to filter links for articles/blogs/guides.

## Setup
1. Install dependencies (including Scrapy and google-generativeai):
   ```
   pip install -r requirements.txt
   ```
2. Set your Gemini API key in the environment:
   ```
   export GEMINI_API_KEY=your-key-here
   ```
3. Start the backend:
   ```
   uvicorn server:app --host 0.0.0.0 --port 8000
   ```

## Usage
- Use the `/api/scrapy-crawl` endpoint (see frontend for UI integration)
- Results are returned as JSON, with logs for debugging

## Notes
- By default, Scrapy obeys robots.txt. You can disable this in the spider for testing.
- If you see errors about Scrapy not found, ensure it is installed in your backend venv and available in PATH. 