import scrapy
from urllib.parse import urljoin
from gemini_crawler.items import GeminiCrawlerItem
import os
import requests

# Import Gemini API (google-generativeai)
import google.generativeai as genai

gemini_api_key = os.environ.get('GEMINI_API_KEY')
gemini_model = None
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel('gemini-2.0-flash-lite')

class GeminiSpider(scrapy.Spider):
    name = 'gemini_spider'
    custom_settings = {
        'DOWNLOAD_DELAY': 0.5,
        'ROBOTSTXT_OBEY': False,  # Ignore robots.txt for bulk scraping
    }

    def __init__(self, start_url=None, max_links=10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url] if start_url else []
        self.max_links = int(max_links)
        self.visited = set()

    def parse(self, response):
        # Collect all links on the page
        links = set()
        for href in response.css('a::attr(href)').getall():
            full_url = urljoin(response.url, href)
            if full_url not in self.visited:
                links.add(full_url)
        links = list(links)[:self.max_links]
        # Use Gemini to filter links
        for link in links:
            is_article = self.is_article_link_gemini(link)
            print(f"[GeminiSpider] Link: {link} | Is Article: {is_article}")
            if is_article:
                yield scrapy.Request(link, callback=self.parse_article)
            self.visited.add(link)

    def is_article_link_gemini(self, url):
        import re
        if not gemini_model:
            return True  # fallback: allow all
        prompt = f"""
        Given the following URL, is it likely to be a blog post, article, or guide (not a homepage, tag, category, or resource page)? 
        If the URL points to a specific post or article, respond with: {{\"is_blog_link\": true}}. 
        If not, respond with: {{\"is_blog_link\": false}}.
        URL: {url}
        Respond with only the JSON object.
        """
        try:
            response = gemini_model.generate_content(prompt)
            if response and response.text:
                print(f"[GeminiSpider] Gemini raw response for {url}: {response.text}")
                import json
                result = json.loads(response.text.strip().split('\n')[0])
                return bool(result.get("is_blog_link", False))
        except Exception as e:
            print(f"[GeminiSpider] Gemini error for {url}: {e}")
        # Fallback: simple heuristic
        if re.search(r'/\\d{4}/\\d{2}/', url) or url.endswith('.html'):
            print(f"[GeminiSpider] Heuristic matched for {url}: True")
            return True
        print(f"[GeminiSpider] Heuristic matched for {url}: False")
        return False

    def parse_article(self, response):
        # Simple extraction: get title and main text
        item = GeminiCrawlerItem()
        item['url'] = response.url
        item['title'] = response.css('title::text').get() or ''
        item['content'] = ' '.join(response.css('body *::text').getall()).strip()
        item['author'] = ''
        item['category'] = 'article'
        yield item 