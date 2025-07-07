from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import tempfile
import asyncio
import aiofiles
import json

# Scraping libraries
import newspaper
from newspaper import Article
import trafilatura
import fitz  # PyMuPDF
import pdfplumber
from markdownify import markdownify as md
from bs4 import BeautifulSoup
import html2text
from readability import Document
import requests
from urllib.parse import urlparse, urljoin, urlunparse
import re
from typing import Set, Dict, Any


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

class ScrapedContent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str  # Markdown format
    content_type: str  # 'blog', 'article', 'pdf', 'guide', etc.
    source_url: Optional[str] = None
    author: Optional[str] = None
    user_id: Optional[str] = None
    team_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    word_count: int = 0
    extraction_method: str = ""  # 'newspaper', 'trafilatura', 'pymupdf', etc.

class ScrapeUrlRequest(BaseModel):
    url: str
    team_id: str
    user_id: Optional[str] = None
    content_type: Optional[str] = "blog"

class ScrapeResponse(BaseModel):
    success: bool
    message: str
    data: Optional[ScrapedContent] = None

class BulkScrapeRequest(BaseModel):
    url: str
    team_id: str
    user_id: Optional[str] = None
    max_depth: int = 1  # How deep to follow links
    max_links: int = 10  # Maximum number of links to follow
    include_base_url: bool = True  # Whether to include the original URL in results

class BulkScrapeResponse(BaseModel):
    team_id: str
    items: List[ScrapedContent]


class ContentScraper:
    def __init__(self):
        self.h = html2text.HTML2Text()
        self.h.ignore_links = False
        self.h.ignore_images = False
        self.h.body_width = 0
        
    def _is_valid_blog_link(self, url: str, base_domain: str) -> bool:
        """
        Check if a URL is likely a blog post or article link
        """
        try:
            parsed = urlparse(url)
            
            # Skip non-HTTP links
            if not parsed.scheme in ['http', 'https']:
                return False
            
            # Skip external domains (optional - you can modify this)
            if parsed.netloc and parsed.netloc != base_domain:
                return False
            
            # Skip common non-article paths
            skip_patterns = [
                r'/tag/', r'/category/', r'/author/', r'/search/',
                r'/about', r'/contact', r'/privacy', r'/terms',
                r'/wp-admin/', r'/wp-content/', r'/feed',
                r'\.css$', r'\.js$', r'\.png$', r'\.jpg$', r'\.jpeg$', r'\.gif$', r'\.pdf$',
                r'#', r'mailto:', r'tel:', r'javascript:',
                r'/page/\d+', r'/\d{4}/$', r'/\d{4}/\d{2}/$'  # pagination and date archives
            ]
            
            for pattern in skip_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return False
            
            # Look for positive indicators
            article_patterns = [
                r'/\d{4}/\d{2}/\d{2}/',  # Date-based URLs
                r'/posts?/', r'/articles?/', r'/blog/',
                r'/\d+/', r'/[a-zA-Z0-9-]+/$'  # Slug-based URLs
            ]
            
            for pattern in article_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
            
            # Default: if it has a meaningful path (not just domain), consider it
            if parsed.path and len(parsed.path) > 1 and not parsed.path.endswith('/'):
                return True
                
            return False
            
        except Exception:
            return False
    
    def _extract_links_from_content(self, html_content: str, base_url: str) -> List[str]:
        """
        Extract potential blog/article links from HTML content
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            links = []
            base_domain = urlparse(base_url).netloc
            
            # Find all links
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                if not href:
                    continue
                
                # Convert relative URLs to absolute
                full_url = urljoin(base_url, href)
                
                # Check if it's a valid blog link
                if self._is_valid_blog_link(full_url, base_domain):
                    links.append(full_url)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_links = []
            for link in links:
                if link not in seen:
                    seen.add(link)
                    unique_links.append(link)
            
            return unique_links
            
        except Exception as e:
            logging.warning(f"Failed to extract links from content: {e}")
            return []
    
    async def bulk_scrape_with_links(self, url: str, team_id: str, user_id: Optional[str] = None, 
                                   max_depth: int = 1, max_links: int = 10, 
                                   include_base_url: bool = True) -> BulkScrapeResponse:
        """
        Scrape a URL and discover/follow links to scrape additional content
        """
        scraped_items = []
        processed_urls = set()
        
        try:
            # Step 1: Scrape the base URL
            if include_base_url:
                try:
                    base_content = await self.scrape_url(url, team_id, user_id, "blog")
                    scraped_items.append(base_content)
                    processed_urls.add(url)
                except Exception as e:
                    logging.warning(f"Failed to scrape base URL {url}: {e}")
            
            # Step 2: Extract links from the base URL
            if max_depth > 0 and max_links > 0:
                try:
                    # Get HTML content for link extraction
                    response = requests.get(url, timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    })
                    response.raise_for_status()
                    
                    # Extract links
                    discovered_links = self._extract_links_from_content(response.text, url)
                    
                    # Limit the number of links to process
                    discovered_links = discovered_links[:max_links]
                    
                    # Step 3: Scrape discovered links
                    for link in discovered_links:
                        if link in processed_urls:
                            continue
                        
                        try:
                            # Determine content type based on URL
                            content_type = "blog"
                            if "podcast" in link.lower():
                                content_type = "podcast_transcript"
                            elif "linkedin" in link.lower():
                                content_type = "linkedin_post"
                            elif "reddit" in link.lower():
                                content_type = "reddit_comment"
                            
                            link_content = await self.scrape_url(link, team_id, user_id, content_type)
                            scraped_items.append(link_content)
                            processed_urls.add(link)
                            
                            # Small delay to be respectful to servers
                            await asyncio.sleep(0.5)
                            
                        except Exception as e:
                            logging.warning(f"Failed to scrape discovered link {link}: {e}")
                            continue
                    
                except Exception as e:
                    logging.warning(f"Failed to extract links from {url}: {e}")
            
            # Step 4: Save all scraped content to database
            for item in scraped_items:
                try:
                    await db.scraped_content.insert_one(item.dict())
                except Exception as e:
                    logging.warning(f"Failed to save item {item.id} to database: {e}")
            
            return BulkScrapeResponse(
                team_id=team_id,
                items=scraped_items
            )
            
        except Exception as e:
            logging.error(f"Bulk scraping failed for {url}: {e}")
            raise HTTPException(status_code=500, detail=f"Bulk scraping failed: {str(e)}")
        
    async def scrape_url(self, url: str, team_id: str, user_id: Optional[str] = None, content_type: str = "blog") -> ScrapedContent:
        """
        Scrape content from a URL using multiple methods for best results
        """
        try:
            # Method 1: Try newspaper3k first
            try:
                article = Article(url)
                article.download()
                article.parse()
                
                if article.text and len(article.text.strip()) > 50:  # Lower threshold
                    content_markdown = self._clean_and_convert_to_markdown(article.text)
                    word_count = len(article.text.split())
                    
                    logging.info(f"Newspaper3k extracted {word_count} words from {url}")
                    
                    return ScrapedContent(
                        title=article.title or self._extract_title_from_url(url),
                        content=content_markdown,
                        content_type=content_type,
                        source_url=url,
                        author=", ".join(article.authors) if article.authors else None,
                        user_id=user_id,
                        team_id=team_id,
                        word_count=word_count,
                        extraction_method="newspaper3k"
                    )
            except Exception as e:
                logging.warning(f"Newspaper3k failed for {url}: {e}")
            
            # Method 2: Try trafilatura
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                    if text and len(text.strip()) > 50:  # Lower threshold
                        content_markdown = self._clean_and_convert_to_markdown(text)
                        word_count = len(text.split())
                        
                        # Try to extract metadata
                        metadata = trafilatura.extract_metadata(downloaded)
                        title = metadata.title if metadata and metadata.title else self._extract_title_from_url(url)
                        author = metadata.author if metadata and metadata.author else None
                        
                        logging.info(f"Trafilatura extracted {word_count} words from {url}")
                        
                        return ScrapedContent(
                            title=title,
                            content=content_markdown,
                            content_type=content_type,
                            source_url=url,
                            author=author,
                            user_id=user_id,
                            team_id=team_id,
                            word_count=word_count,
                            extraction_method="trafilatura"
                        )
            except Exception as e:
                logging.warning(f"Trafilatura failed for {url}: {e}")
            
            # Method 3: Fallback to requests + readability
            try:
                response = requests.get(url, timeout=30, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                })
                response.raise_for_status()
                
                doc = Document(response.text)
                title = doc.title()
                content_html = doc.summary()
                
                if content_html and len(content_html.strip()) > 50:  # Lower threshold
                    content_markdown = self.h.handle(content_html)
                    content_markdown = self._clean_markdown(content_markdown)
                    word_count = len(content_markdown.split())
                    
                    logging.info(f"Readability extracted {word_count} words from {url}")
                    
                    return ScrapedContent(
                        title=title or self._extract_title_from_url(url),
                        content=content_markdown,
                        content_type=content_type,
                        source_url=url,
                        author=None,
                        user_id=user_id,
                        team_id=team_id,
                        word_count=word_count,
                        extraction_method="readability"
                    )
            except Exception as e:
                logging.warning(f"Readability method failed for {url}: {e}")
            
            raise Exception("All extraction methods failed")
            
        except Exception as e:
            logging.error(f"Failed to scrape {url}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to scrape content from URL: {str(e)}")
    
    async def scrape_pdf(self, file_content: bytes, filename: str, team_id: str, user_id: Optional[str] = None) -> ScrapedContent:
        """
        Extract text from PDF using multiple methods
        """
        try:
            # Method 1: Try PyMuPDF first
            try:
                doc = fitz.open(stream=file_content, filetype="pdf")
                text_content = ""
                
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    text_content += page.get_text() + "\n\n"
                
                doc.close()
                
                if text_content.strip() and len(text_content.strip()) > 100:
                    content_markdown = self._clean_and_convert_to_markdown(text_content)
                    word_count = len(text_content.split())
                    
                    return ScrapedContent(
                        title=filename.replace('.pdf', ''),
                        content=content_markdown,
                        content_type="pdf",
                        source_url=None,
                        author=None,
                        user_id=user_id,
                        team_id=team_id,
                        word_count=word_count,
                        extraction_method="pymupdf"
                    )
            except Exception as e:
                logging.warning(f"PyMuPDF failed for {filename}: {e}")
            
            # Method 2: Try pdfplumber
            try:
                with pdfplumber.open(file_content) as pdf:
                    text_content = ""
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_content += page_text + "\n\n"
                
                if text_content.strip() and len(text_content.strip()) > 100:
                    content_markdown = self._clean_and_convert_to_markdown(text_content)
                    word_count = len(text_content.split())
                    
                    return ScrapedContent(
                        title=filename.replace('.pdf', ''),
                        content=content_markdown,
                        content_type="pdf",
                        source_url=None,
                        author=None,
                        user_id=user_id,
                        team_id=team_id,
                        word_count=word_count,
                        extraction_method="pdfplumber"
                    )
            except Exception as e:
                logging.warning(f"pdfplumber failed for {filename}: {e}")
            
            raise Exception("All PDF extraction methods failed")
            
        except Exception as e:
            logging.error(f"Failed to extract text from PDF {filename}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to extract text from PDF: {str(e)}")
    
    def _clean_and_convert_to_markdown(self, text: str) -> str:
        """Clean and convert text to markdown format"""
        # Basic cleaning
        text = text.strip()
        
        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Convert to markdown-like format
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                processed_lines.append('')
                continue
                
            # Detect headers (simple heuristic)
            if len(line) < 100 and line.isupper():
                processed_lines.append(f"## {line.title()}")
            elif len(line) < 80 and not line.endswith('.') and not line.endswith(',') and not line.endswith(';'):
                # Possible header
                processed_lines.append(f"### {line}")
            else:
                processed_lines.append(line)
        
        return '\n'.join(processed_lines)
    
    def _clean_markdown(self, markdown_text: str) -> str:
        """Clean markdown text"""
        # Remove excessive whitespace
        markdown_text = re.sub(r'\n\s*\n\s*\n', '\n\n', markdown_text)
        markdown_text = re.sub(r'[ \t]+', ' ', markdown_text)
        
        # Remove empty links
        markdown_text = re.sub(r'\[\]\([^)]*\)', '', markdown_text)
        
        return markdown_text.strip()
    
    def _extract_title_from_url(self, url: str) -> str:
        """Extract title from URL as fallback"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        if path:
            return path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
        return parsed.netloc.replace('www.', '').title()


# Initialize scraper
scraper = ContentScraper()


# Original routes
@api_router.get("/")
async def root():
    return {"message": "Technical Content Scraper API"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    _ = await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]


# New scraping routes
@api_router.post("/bulk-scrape", response_model=BulkScrapeResponse)
async def bulk_scrape_endpoint(request: BulkScrapeRequest):
    """
    Scrape a URL and discover/follow links to scrape additional content
    """
    try:
        result = await scraper.bulk_scrape_with_links(
            url=request.url,
            team_id=request.team_id,
            user_id=request.user_id,
            max_depth=request.max_depth,
            max_links=request.max_links,
            include_base_url=request.include_base_url
        )
        
        return result
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulk scraping failed: {str(e)}")


@api_router.post("/scrape-url", response_model=ScrapeResponse)
async def scrape_url_endpoint(request: ScrapeUrlRequest):
    """
    Scrape content from a URL
    """
    try:
        scraped_content = await scraper.scrape_url(
            url=request.url,
            team_id=request.team_id,
            user_id=request.user_id,
            content_type=request.content_type
        )
        
        # Save to database
        await db.scraped_content.insert_one(scraped_content.dict())
        
        return ScrapeResponse(
            success=True,
            message="Content scraped successfully",
            data=scraped_content
        )
    
    except HTTPException as e:
        return ScrapeResponse(
            success=False,
            message=str(e.detail),
            data=None
        )
    except Exception as e:
        return ScrapeResponse(
            success=False,
            message=f"Unexpected error: {str(e)}",
            data=None
        )


@api_router.post("/scrape-pdf", response_model=ScrapeResponse)
async def scrape_pdf_endpoint(
    team_id: str = Form(...),
    user_id: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    """
    Extract text from uploaded PDF
    """
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
        # Read file content
        file_content = await file.read()
        
        if len(file_content) > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(status_code=400, detail="File too large (max 50MB)")
        
        scraped_content = await scraper.scrape_pdf(
            file_content=file_content,
            filename=file.filename,
            team_id=team_id,
            user_id=user_id
        )
        
        # Save to database
        await db.scraped_content.insert_one(scraped_content.dict())
        
        return ScrapeResponse(
            success=True,
            message="PDF content extracted successfully",
            data=scraped_content
        )
    
    except HTTPException as e:
        return ScrapeResponse(
            success=False,
            message=str(e.detail),
            data=None
        )
    except Exception as e:
        return ScrapeResponse(
            success=False,
            message=f"Unexpected error: {str(e)}",
            data=None
        )


@api_router.get("/knowledge-base", response_model=List[ScrapedContent])
async def get_knowledge_base(team_id: str, user_id: Optional[str] = None):
    """
    Get all scraped content for a team/user
    """
    try:
        query = {"team_id": team_id}
        if user_id:
            query["user_id"] = user_id
        
        content_list = await db.scraped_content.find(query).sort("created_at", -1).to_list(1000)
        return [ScrapedContent(**content) for content in content_list]
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch knowledge base: {str(e)}")


@api_router.delete("/knowledge-base/{content_id}")
async def delete_content(content_id: str, team_id: str):
    """
    Delete a specific piece of content
    """
    try:
        result = await db.scraped_content.delete_one({"id": content_id, "team_id": team_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Content not found")
        
        return {"message": "Content deleted successfully"}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete content: {str(e)}")


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()