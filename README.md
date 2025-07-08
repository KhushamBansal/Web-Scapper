# Technical Content Scraper

This project extracts and stores technical knowledge from blogs, guides, and PDFs using FastAPI (backend), React (frontend), and now Scrapy (for high-performance crawling) with Gemini AI integration for smart link filtering.

## Features
- Scrape single URLs, bulk scrape with link discovery, or upload PDFs
- High-performance crawling with Scrapy + Gemini (smart link filtering)
- Knowledge base for storing and managing extracted content

## New: Scrapy Gemini Crawl
- Uses Scrapy for fast, parallel crawling
- Uses Gemini AI to filter links for articles, blogs, and guides
- Integrated into the frontend as a dedicated tab
- Results and logs are shown in the UI, and can be downloaded as JSON

## How to Use
1. **Backend:**
   - Start FastAPI backend as usual:
     ```
     uvicorn server:app --host 0.0.0.0 --port 8000
     ```
   - Ensure Scrapy is installed in your backend virtual environment.
   - Set your Gemini API key in the environment (GEMINI_API_KEY).
2. **Frontend:**
   - Start the React frontend:
     ```
     cd frontend
     npm start
     ```
   - Use the "Scrapy Gemini Crawl" tab to run high-performance crawls.

## Scrapy Notes
- By default, Scrapy obeys robots.txt. You can disable this in the spider for testing.
- The spider is located in `backend/gemini_crawler/gemini_crawler/spiders/gemini_spider.py`.

## Gemini Integration
- Gemini is used to decide which links are likely articles/blogs/guides.
- Requires a valid Gemini API key.

## Troubleshooting
- If you see errors about Scrapy not running, ensure it is installed and available in your backend venv.
- If no items are scraped, check robots.txt or try a different site.
