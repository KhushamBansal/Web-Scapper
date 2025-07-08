from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import tempfile
import asyncio
import aiofiles
import json
import io
import re

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
import requests
from typing import Set, Any

# Gemini AI
import google.generativeai as genai
import subprocess


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Configure Gemini AI
gemini_api_key = os.environ.get('GEMINI_API_KEY')
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)
    logging.info("Gemini AI configured successfully")
else:
    logging.warning("Gemini API key not found")

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
        
        # Initialize Gemini model
        self.gemini_model = None
        if gemini_api_key:
            try:
                self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-lite')
                logging.info("Gemini model initialized successfully")
            except Exception as e:
                logging.warning(f"Failed to initialize Gemini model: {e}")
    
    def _enhance_content_with_gemini(self, raw_content: str, url: str) -> Dict[str, Any]:
        """
        Use Gemini AI to enhance and categorize content
        """
        try:
            if not self.gemini_model or not raw_content.strip():
                return {"content": raw_content, "category": "blog", "enhanced": False}
            
            prompt = f"""
            Analyze and enhance this web content. Return a JSON response with:
            1. "content": Clean, well-formatted markdown content (preserve all important information)
            2. "category": Content type (blog, tutorial, news, documentation, guide, research, podcast_transcript, linkedin_post, reddit_comment, book, other)
            3. "title": Improved title if needed
            4. "author": Extract author name if mentioned
            5. "summary": Brief 2-3 sentence summary
            
            URL: {url}
            
            Raw Content:
            {raw_content[:8000]}  # Limit to avoid token limits
            
            Return only valid JSON:
            """
            
            response = self.gemini_model.generate_content(prompt)
            
            if response and response.text:
                # Try to parse JSON response
                import json
                try:
                    result = json.loads(response.text.strip())
                    result["enhanced"] = True
                    return result
                except json.JSONDecodeError:
                    # If not JSON, try to extract content between JSON markers
                    text = response.text.strip()
                    if "```json" in text:
                        json_start = text.find("```json") + 7
                        json_end = text.find("```", json_start)
                        if json_end > json_start:
                            try:
                                result = json.loads(text[json_start:json_end])
                                result["enhanced"] = True
                                return result
                            except:
                                pass
                    
                    # Fallback: return enhanced content as markdown
                    return {
                        "content": text,
                        "category": "blog", 
                        "enhanced": True,
                        "title": None,
                        "author": None,
                        "summary": None
                    }
                    
        except Exception as e:
            logging.warning(f"Gemini enhancement failed: {e}")
        
        return {"content": raw_content, "category": "blog", "enhanced": False}
    
    def _extract_content_with_gemini(self, url: str) -> Dict[str, Any]:
        """
        Use Gemini as a fallback to extract content when traditional methods fail
        """
        try:
            if not self.gemini_model:
                return None
            
            # Get raw HTML
            response = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            # Limit HTML size to avoid token limits
            html_content = response.text[:15000]
            
            prompt = f"""
            Extract the main content from this HTML webpage and return clean markdown. 
            Focus on the article/blog content, ignore navigation, ads, comments, etc.
            
            URL: {url}
            
            Return JSON with:
            {{
                "title": "Article title",
                "content": "Full article content in markdown format",
                "author": "Author name if found",
                "category": "content type (blog, tutorial, news, etc.)"
            }}
            
            HTML:
            {html_content}
            """
            
            ai_response = self.gemini_model.generate_content(prompt)
            
            if ai_response and ai_response.text:
                import json
                try:
                    result = json.loads(ai_response.text.strip())
                    return result
                except json.JSONDecodeError:
                    # Try to extract JSON from response
                    text = ai_response.text.strip()
                    if "```json" in text:
                        json_start = text.find("```json") + 7
                        json_end = text.find("```", json_start)
                        if json_end > json_start:
                            try:
                                return json.loads(text[json_start:json_end])
                            except:
                                pass
                    
                    # Fallback: treat as markdown content
                    return {
                        "title": self._extract_title_from_url(url),
                        "content": text,
                        "author": None,
                        "category": "blog"
                    }
                    
        except Exception as e:
            logging.warning(f"Gemini extraction failed for {url}: {e}")
        
        return None
        
    def _is_valid_blog_link(self, url: str, base_domain: str) -> bool:
        """
        Use Gemini API to decide if a URL is likely a blog post or article link. Fallback to old logic if Gemini is unavailable.
        """
        try:
            # Use Gemini if available
            if self.gemini_model:
                prompt = f"""
                Given the following URL and base domain, decide if the URL is likely a blog post, article, or guide (not a homepage, tag, category, or resource page). Return true or false as JSON.
                Base domain: {base_domain}
                URL: {url}
                Respond with: {{"is_blog_link": true}} or {{"is_blog_link": false}}
                """
                response = self.gemini_model.generate_content(prompt)
                if response and response.text:
                    import json
                    try:
                        result = json.loads(response.text.strip().split('\n')[0])
                        return bool(result.get("is_blog_link", False))
                    except Exception:
                        pass
            # Fallback to old logic
            parsed = urlparse(url)
            if not parsed.scheme in ['http', 'https']:
                return False
            skip_patterns = [
                r'/tag/', r'/category/', r'/author/', r'/search/',
                r'/about', r'/contact', r'/privacy', r'/terms',
                r'/wp-admin/', r'/wp-content/', r'/feed',
                r'\.css$', r'\.js$', r'\.png$', r'\.jpg$', r'\.jpeg$', r'\.gif$', r'\.pdf$',
                r'#', r'mailto:', r'tel:', r'javascript:',
                r'/page/\d+', r'/\d{4}/$', r'/\d{4}/\d{2}/$'
            ]
            for pattern in skip_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return False
            article_patterns = [
                r'/\d{4}/\d{2}/\d{2}/',  # Date-based URLs
                r'/posts?/', r'/articles?/', r'/blog/',
                r'/\d+/', r'/[a-zA-Z0-9-]+/$'  # Slug-based URLs
            ]
            for pattern in article_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
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
        link_decisions = []
        try:
            # Step 1: Scrape the base URL
            if include_base_url:
                try:
                    base_content = await self.scrape_url(url, team_id, user_id, "blog")
                    scraped_items.append(base_content)
                    processed_urls.add(url)
                except Exception as e:
                    logging.warning(f"Failed to scrape base URL {url}: {e}")
            # Step 2: Extract all links from the base URL (no filtering)
            if max_depth > 0 and max_links > 0:
                try:
                    response = requests.get(url, timeout=30, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    })
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')
                    all_links = []
                    for link in soup.find_all('a', href=True):
                        href = link.get('href')
                        if not href:
                            continue
                        full_url = urljoin(url, href)
                        if full_url not in all_links:
                            all_links.append(full_url)
                    # Limit the number of links to process
                    all_links = all_links[:max_links]
                    # Step 3: Use Gemini to check if each link is an article/blog/guide
                    for link in all_links:
                        if link in processed_urls:
                            continue
                        is_article = False
                        if self.gemini_model:
                            prompt = f"""
                            Is the following URL likely to be a blog post, article, or guide (not a homepage, tag, category, or resource page)? Return true or false as JSON.\nURL: {link}\nRespond with: {{\"is_blog_link\": true}} or {{\"is_blog_link\": false}}"""
                            response = self.gemini_model.generate_content(prompt)
                            if response and response.text:
                                import json
                                try:
                                    result = json.loads(response.text.strip().split('\n')[0])
                                    is_article = bool(result.get("is_blog_link", False))
                                except Exception:
                                    pass
                        # Save decision for debugging/inspection
                        link_decisions.append({"url": link, "is_article": is_article})
                        if is_article:
                            try:
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
            # Optionally, you can return link_decisions for debugging
            return BulkScrapeResponse(
                team_id=team_id,
                items=scraped_items
            )
        except Exception as e:
            logging.error(f"Bulk scraping failed for {url}: {e}")
            raise HTTPException(status_code=500, detail=f"Bulk scraping failed: {str(e)}")
        
    async def scrape_url(self, url: str, team_id: str, user_id: Optional[str] = None, content_type: str = "blog") -> ScrapedContent:
        """
        Scrape content from a URL using multiple methods for best results, enhanced with Gemini AI
        """
        try:
            best_content = None
            best_word_count = 0
            extraction_methods_tried = []
            # Method 1: Try newspaper3k first
            try:
                article = Article(url)
                article.download()
                article.parse()
                if article.text and len(article.text.strip()) > 50:
                    word_count = len(article.text.split())
                    if word_count > best_word_count:
                        best_content = {
                            "title": article.title or self._extract_title_from_url(url),
                            "content": article.text,
                            "author": ", ".join(article.authors) if article.authors else None,
                            "method": "newspaper3k",
                            "word_count": word_count
                        }
                        best_word_count = word_count
                    extraction_methods_tried.append("newspaper3k")
                    logging.info(f"Newspaper3k extracted {word_count} words from {url}")
            except Exception as e:
                logging.warning(f"Newspaper3k failed for {url}: {e}")
            # Method 2: Try trafilatura
            try:
                downloaded = trafilatura.fetch_url(url)
                if downloaded:
                    text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
                    if text and len(text.strip()) > 50:
                        word_count = len(text.split())
                        if word_count > best_word_count:
                            metadata = trafilatura.extract_metadata(downloaded)
                            title = metadata.title if metadata and metadata.title else self._extract_title_from_url(url)
                            author = metadata.author if metadata and metadata.author else None
                            best_content = {
                                "title": title,
                                "content": text,
                                "author": author,
                                "method": "trafilatura",
                                "word_count": word_count
                            }
                            best_word_count = word_count
                        extraction_methods_tried.append("trafilatura")
                        logging.info(f"Trafilatura extracted {word_count} words from {url}")
            except Exception as e:
                logging.warning(f"Trafilatura failed for {url}: {e}")
            # Method 3: Try requests + readability with advanced headers
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Referer': url,
                    'DNT': '1',
                    'Upgrade-Insecure-Requests': '1',
                }
                response = requests.get(url, timeout=30, headers=headers)
                response.raise_for_status()
                doc = Document(response.text)
                title = doc.title()
                content_html = doc.summary()
                if content_html and len(content_html.strip()) > 50:
                    content_text = self.h.handle(content_html)
                    content_text = self._clean_markdown(content_text)
                    word_count = len(content_text.split())
                    if word_count > best_word_count:
                        best_content = {
                            "title": title or self._extract_title_from_url(url),
                            "content": content_text,
                            "author": None,
                            "method": "readability",
                            "word_count": word_count
                        }
                        best_word_count = word_count
                    extraction_methods_tried.append("readability")
                    logging.info(f"Readability extracted {word_count} words from {url}")
            except Exception as e:
                logging.warning(f"Readability method failed for {url}: {e}")
            # Method 4: Gemini AI Fallback (if other methods failed or returned poor results)
            if (not best_content or best_word_count < 100) and self.gemini_model:
                try:
                    # Try Gemini with a direct fetch prompt
                    prompt = f"""
                    Fetch the content from the following URL and extract the main article, blog post, or guide. Return the result as JSON with keys: title, content (markdown), author (if found), and category. If the page is not accessible, return an error message.
                    URL: {url}
                    """
                    ai_response = self.gemini_model.generate_content(prompt)
                    if ai_response and ai_response.text:
                        import json
                        try:
                            result = json.loads(ai_response.text.strip().split('\n')[0])
                            if result.get("content"):
                                best_content = {
                                    "title": result.get("title") or self._extract_title_from_url(url),
                                    "content": result["content"],
                                    "author": result.get("author"),
                                    "method": "gemini-direct-fetch",
                                    "word_count": len(result["content"].split())
                                }
                                best_word_count = best_content["word_count"]
                                extraction_methods_tried.append("gemini-direct-fetch")
                        except Exception:
                            pass
                except Exception as e:
                    logging.warning(f"Gemini direct fetch failed for {url}: {e}")
            if not best_content:
                raise Exception(f"All extraction methods failed. Tried: {', '.join(extraction_methods_tried)}")
            # Enhance content with Gemini if available and content is decent
            enhanced_result = self._enhance_content_with_gemini(best_content["content"], url)
            if enhanced_result.get("enhanced"):
                final_content = enhanced_result.get("content", best_content["content"])
                final_title = enhanced_result.get("title") or best_content["title"]
                final_author = enhanced_result.get("author") or best_content["author"]
                final_content_type = enhanced_result.get("category", content_type)
                extraction_method = f"{best_content['method']}+gemini"
            else:
                final_content = self._clean_and_convert_to_markdown(best_content["content"])
                final_title = best_content["title"]
                final_author = best_content["author"]
                final_content_type = content_type
                extraction_method = best_content["method"]
            final_word_count = len(final_content.split())
            logging.info(f"Final extraction: {final_word_count} words via {extraction_method}")
            return ScrapedContent(
                title=final_title,
                content=final_content,
                content_type=final_content_type,
                source_url=url,
                author=final_author,
                user_id=user_id,
                team_id=team_id,
                word_count=final_word_count,
                extraction_method=extraction_method
            )
        except Exception as e:
            logging.error(f"Failed to scrape {url}: {e}")
            raise HTTPException(status_code=400, detail=f"Failed to scrape content from URL: {str(e)}")
    
    async def scrape_pdf(self, file_content: bytes, filename: str, team_id: str, user_id: str = None) -> List[Dict]:
        """Extract text from PDF, split into logical chunks, and return as a list of markdown items."""
        items = []
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                # 1. Try to detect TOC and chunk by it
                toc = self._detect_toc(pdf)
                if toc:
                    for i, (title, start_page) in enumerate(toc):
                        end_page = toc[i+1][1] if i+1 < len(toc) else len(pdf.pages)
                        content = self._extract_text_range(pdf, start_page, end_page)
                        if len(content.strip()) > 50:
                            items.append({
                                "title": title,
                                "content": self._clean_and_convert_to_markdown(content),
                                "content_type": "book",
                                "source_url": filename,
                                "author": "",
                                "user_id": user_id or ""
                            })
                    if items:
                        return items
                # 2. Try to chunk by headings
                heading_chunks = self._chunk_by_headings(pdf)
                if len(heading_chunks) >= 3:
                    for i, (title, content, page_range) in enumerate(heading_chunks):
                        if len(content.strip()) > 50:
                            items.append({
                                "title": title or f"Section {i+1} (pages {page_range})",
                                "content": self._clean_and_convert_to_markdown(content),
                                "content_type": "book",
                                "source_url": filename,
                                "author": "",
                                "user_id": user_id or ""
                            })
                    if items:
                        return items
                # 3. Fallback: adaptive chunking by content size
                adaptive_chunks = self._adaptive_chunking(pdf)
                for i, (content, page_range) in enumerate(adaptive_chunks):
                    if len(content.strip()) > 50:
                        items.append({
                            "title": f"Chunk {i+1} (pages {page_range})",
                            "content": self._clean_and_convert_to_markdown(content),
                            "content_type": "book",
                            "source_url": filename,
                            "author": "",
                            "user_id": user_id or ""
                        })
        except Exception as e:
            logging.error(f"Failed to scrape PDF {filename}: {e}")
        return items

    def _detect_toc(self, pdf) -> List:
        toc = []
        toc_pattern = re.compile(r'([A-Z][\w\s\-:]+)\s+\.{2,}\s*(\d+)$')
        for page_num in range(min(10, len(pdf.pages))):
            text = pdf.pages[page_num].extract_text() or ""
            for line in text.splitlines():
                match = toc_pattern.match(line.strip())
                if match:
                    title = match.group(1).strip()
                    page = int(match.group(2)) - 1
                    if len(title) > 5 and 0 <= page < len(pdf.pages):
                        toc.append((title, page))
        return sorted(toc, key=lambda x: x[1]) if len(toc) >= 3 else []

    def _extract_text_range(self, pdf, start_page: int, end_page: int) -> str:
        content = ""
        for i in range(start_page, min(end_page, len(pdf.pages))):
            page_text = pdf.pages[i].extract_text() or ""
            content += page_text + "\n"
        return content

    def _chunk_by_headings(self, pdf) -> List:
        chunks = []
        current_title = None
        current_content = ""
        start_page = 0
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = text.splitlines()
            found_heading = False
            for line in lines:
                line = line.strip()
                if (line.isupper() and len(line) > 5) or re.match(r'^\d+\.\s+[A-Z]', line):
                    if current_content.strip():
                        chunks.append((current_title, current_content.strip(), f"{start_page+1}-{i}"))
                    current_title = line
                    current_content = ""
                    start_page = i
                    found_heading = True
                    break
            if not found_heading:
                current_content += text + "\n"
        if current_content.strip():
            chunks.append((current_title, current_content.strip(), f"{start_page+1}-{len(pdf.pages)}"))
        return chunks

    def _adaptive_chunking(self, pdf, target_chunk_size=8000) -> List:
        chunks = []
        current_content = ""
        start_page = 0
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            current_content += text + "\n"
            if len(current_content) > target_chunk_size:
                chunks.append((current_content.strip(), f"{start_page+1}-{i+1}"))
                current_content = ""
                start_page = i + 1
        if current_content.strip():
            chunks.append((current_content.strip(), f"{start_page+1}-{len(pdf.pages)}"))
        return chunks
    
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
        # Normalize URL: prepend https:// if missing scheme
        url = request.url
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url.lstrip(":/")
        result = await scraper.bulk_scrape_with_links(
            url=url,
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
        # Normalize URL: prepend https:// if missing scheme
        url = request.url
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url.lstrip(":/")
        scraped_content = await scraper.scrape_url(
            url=url,
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


@api_router.post("/scrape-pdf")
async def scrape_pdf_endpoint(
    team_id: str = Form(...),
    user_id: str = Form(None),
    file: UploadFile = File(...)
):
    """
    Extract text from uploaded PDF, split into chapters/chunks, and return as JSON array
    """
    try:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 50MB)")
        items = await scraper.scrape_pdf(
            file_content=file_content,
            filename=file.filename,
            team_id=team_id,
            user_id=user_id
        )
        return { 'success': True, 'message': 'PDF content extracted and chunked successfully', 'items': items }
    except HTTPException as e:
        return { 'success': False, 'message': str(e.detail), 'items': [] }
    except Exception as e:
        return { 'success': False, 'message': f"Unexpected error: {str(e)}", 'items': [] }


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


@api_router.post("/scrapy-crawl")
async def scrapy_crawl_endpoint(url: str, max_links: int = 10):
    """
    Run the Scrapy Gemini spider on the given URL and return the results as JSON.
    """
    import tempfile
    import os
    import json
    # Create a temporary file for output
    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmpfile:
        output_path = tmpfile.name
    # Build the Scrapy command
    scrapy_cmd = [
        "scrapy", "crawl", "gemini_spider",
        "-a", f"start_url={url}",
        "-a", f"max_links={max_links}",
        "-o", output_path
    ]
    # Run the Scrapy spider as a subprocess
    proc = subprocess.run(scrapy_cmd, cwd="./gemini_crawler", capture_output=True, text=True)
    # Read the output JSON
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        data = []
    # Clean up the temp file
    os.remove(output_path)
    # Optionally, include Scrapy logs in the response for debugging
    return {"results": data, "scrapy_stdout": proc.stdout, "scrapy_stderr": proc.stderr}


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