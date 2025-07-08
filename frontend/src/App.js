import React, { useState, useEffect } from "react";
import "./App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const App = () => {
  const [activeTab, setActiveTab] = useState('url');
  const [url, setUrl] = useState('');
  const [bulkUrl, setBulkUrl] = useState('');
  const [maxLinks, setMaxLinks] = useState(10);
  const [includeBaseUrl, setIncludeBaseUrl] = useState(true);
  const [file, setFile] = useState(null);
  const [teamId, setTeamId] = useState('team-demo-123');
  const [userId, setUserId] = useState('user-demo-456');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [bulkResult, setBulkResult] = useState(null);
  const [error, setError] = useState('');
  const [knowledgeBase, setKnowledgeBase] = useState([]);
  const [showKnowledgeBase, setShowKnowledgeBase] = useState(false);
  const [scrapyUrl, setScrapyUrl] = useState('');
  const [scrapyMaxLinks, setScrapyMaxLinks] = useState(10);
  const [scrapyResult, setScrapyResult] = useState(null);
  const [scrapyLogs, setScrapyLogs] = useState(null);

  const handleBulkScrape = async () => {
    if (!bulkUrl || !teamId) {
      setError('Please enter both URL and Team ID');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);
    setBulkResult(null);

    try {
      const response = await axios.post(`${API}/bulk-scrape`, {
        url: bulkUrl,
        team_id: teamId,
        user_id: userId || null,
        max_depth: 1,
        max_links: maxLinks,
        include_base_url: includeBaseUrl
      });

      setBulkResult(response.data);
      setBulkUrl('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to bulk scrape content');
    } finally {
      setLoading(false);
    }
  };

  const handleUrlScrape = async () => {
    if (!url || !teamId) {
      setError('Please enter both URL and Team ID');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const response = await axios.post(`${API}/scrape-url`, {
        url: url,
        team_id: teamId,
        user_id: userId || null,
        content_type: 'blog'
      });

      if (response.data.success) {
        setResult(response.data.data);
        setUrl('');
      } else {
        setError(response.data.message);
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to scrape URL');
    } finally {
      setLoading(false);
    }
  };

  const handlePdfScrape = async () => {
    if (!file || !teamId) {
      setError('Please select a PDF file and enter Team ID');
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('team_id', teamId);
      if (userId) formData.append('user_id', userId);

      const response = await axios.post(`${API}/scrape-pdf`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      console.log('PDF Extract Response:', response.data); // Debug log

      if (response.data.success) {
        setResult(response.data.items);
        setFile(null);
        // Reset file input
        const fileInput = document.getElementById('pdfFile');
        if (fileInput) fileInput.value = '';
      } else {
        setError(response.data.message);
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to extract PDF content');
    } finally {
      setLoading(false);
    }
  };

  const handleScrapyCrawl = async () => {
    if (!scrapyUrl) {
      setError('Please enter a URL for Scrapy Gemini Crawl');
      return;
    }
    setLoading(true);
    setError('');
    setScrapyResult(null);
    setScrapyLogs(null);
    try {
      const response = await axios.post(`${API}/scrapy-crawl`, null, {
        params: {
          url: scrapyUrl,
          max_links: scrapyMaxLinks
        }
      });
      setScrapyResult(response.data.results);
      setScrapyLogs({stdout: response.data.scrapy_stdout, stderr: response.data.scrapy_stderr});
      setScrapyUrl('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to run Scrapy Gemini Crawl');
    } finally {
      setLoading(false);
    }
  };

  const loadKnowledgeBase = async () => {
    if (!teamId) {
      setError('Please enter Team ID');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await axios.get(`${API}/knowledge-base`, {
        params: {
          team_id: teamId,
          user_id: userId || null
        }
      });

      setKnowledgeBase(response.data);
      setShowKnowledgeBase(true);
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to load knowledge base');
    } finally {
      setLoading(false);
    }
  };

  const deleteContent = async (contentId) => {
    try {
      await axios.delete(`${API}/knowledge-base/${contentId}`, {
        params: { team_id: teamId }
      });
      
      // Refresh knowledge base
      loadKnowledgeBase();
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to delete content');
    }
  };

  const truncateContent = (content, maxLength = 200) => {
    if (content.length <= maxLength) return content;
    return content.substring(0, maxLength) + '...';
  };

  useEffect(() => {
    // Test API connection
    const testConnection = async () => {
      try {
        await axios.get(`${API}/`);
      } catch (err) {
        console.error('API connection test failed:', err);
      }
    };
    testConnection();
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-4xl font-bold text-gray-800 mb-2">
              Technical Content Scraper
            </h1>
            <p className="text-gray-600 text-lg">
              Extract and store technical knowledge from blogs, guides, and PDFs
            </p>
          </div>

          {/* Configuration */}
          <div className="bg-white rounded-lg shadow-lg p-6 mb-8">
            <h2 className="text-xl font-semibold mb-4 text-gray-800">Configuration</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Team ID *
                </label>
                <input
                  type="text"
                  value={teamId}
                  onChange={(e) => setTeamId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Enter team ID"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  User ID (Optional)
                </label>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => setUserId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Enter user ID"
                />
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="bg-white rounded-lg shadow-lg p-6">
            {/* Tabs */}
            <div className="flex border-b border-gray-200 mb-6">
              <button
                className={`py-2 px-4 font-medium ${
                  activeTab === 'url'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setActiveTab('url')}
              >
                Single URL
              </button>
              <button
                className={`py-2 px-4 font-medium ${
                  activeTab === 'bulk'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setActiveTab('bulk')}
              >
                Bulk Scrape
              </button>
              <button
                className={`py-2 px-4 font-medium ${
                  activeTab === 'pdf'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setActiveTab('pdf')}
              >
                Extract PDF
              </button>
              <button
                className={`py-2 px-4 font-medium ${
                  activeTab === 'knowledge'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setActiveTab('knowledge')}
              >
                Knowledge Base
              </button>
              <button
                className={`py-2 px-4 font-medium ${
                  activeTab === 'scrapy'
                    ? 'text-blue-600 border-b-2 border-blue-600'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
                onClick={() => setActiveTab('scrapy')}
              >
                Scrapy Gemini Crawl
              </button>
            </div>

            {/* Single URL Scraping Tab */}
            {activeTab === 'url' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Enter URL to scrape
                  </label>
                  <input
                    type="url"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="https://example.com/blog-post"
                  />
                </div>
                <button
                  onClick={handleUrlScrape}
                  disabled={loading}
                  className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Scraping...' : 'Scrape Single URL'}
                </button>
                <p className="text-sm text-gray-600">
                  Scrape a single URL without following links.
                </p>
              </div>
            )}

            {/* Bulk Scraping Tab */}
            {activeTab === 'bulk' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Enter URL to scrape with link discovery
                  </label>
                  <input
                    type="url"
                    value={bulkUrl}
                    onChange={(e) => setBulkUrl(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="https://example.com/blog-homepage"
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Max Links to Follow
                    </label>
                    <input
                      type="number"
                      value={maxLinks}
                      onChange={(e) => setMaxLinks(parseInt(e.target.value) || 10)}
                      min="1"
                      max="50"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                  <div className="flex items-center space-x-2 pt-6">
                    <input
                      type="checkbox"
                      id="includeBaseUrl"
                      checked={includeBaseUrl}
                      onChange={(e) => setIncludeBaseUrl(e.target.checked)}
                      className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
                    />
                    <label htmlFor="includeBaseUrl" className="text-sm font-medium text-gray-700">
                      Include base URL
                    </label>
                  </div>
                </div>
                <button
                  onClick={handleBulkScrape}
                  disabled={loading}
                  className="bg-purple-600 text-white px-6 py-2 rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Discovering & Scraping...' : 'Bulk Scrape with Links'}
                </button>
                <p className="text-sm text-gray-600">
                  🔥 <strong>Smart Discovery:</strong> Automatically finds and scrapes blog posts, articles, and guides linked from the main page. Perfect for blog homepages, archive pages, or resource collections.
                </p>
              </div>
            )}

            {/* PDF Extraction Tab */}
            {activeTab === 'pdf' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Select PDF file
                  </label>
                  <input
                    type="file"
                    id="pdfFile"
                    accept=".pdf"
                    onChange={(e) => setFile(e.target.files[0])}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <button
                  onClick={handlePdfScrape}
                  disabled={loading}
                  className="bg-green-600 text-white px-6 py-2 rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Extracting...' : 'Extract PDF Content'}
                </button>
                <p className="text-sm text-gray-600">
                  Maximum file size: 50MB. Supports text-based PDFs (not scanned images).
                </p>
              </div>
            )}

            {/* Knowledge Base Tab */}
            {activeTab === 'knowledge' && (
              <div className="space-y-4">
                <button
                  onClick={loadKnowledgeBase}
                  disabled={loading}
                  className="bg-purple-600 text-white px-6 py-2 rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Loading...' : 'Load Knowledge Base'}
                </button>
                
                {knowledgeBase.length > 0 && (
                  <div className="space-y-4">
                    <h3 className="text-lg font-semibold text-gray-800">
                      Stored Content ({knowledgeBase.length} items)
                    </h3>
                    {knowledgeBase.map((item) => (
                      <div key={item.id} className="border border-gray-200 rounded-md p-4">
                        <div className="flex justify-between items-start mb-2">
                          <h4 className="font-medium text-gray-800">{item.title}</h4>
                          <button
                            onClick={() => deleteContent(item.id)}
                            className="text-red-600 hover:text-red-800 text-sm"
                          >
                            Delete
                          </button>
                        </div>
                        <div className="text-sm text-gray-600 mb-2">
                          <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                            {item.content_type}
                          </span>
                          <span className="ml-2">{item.word_count} words</span>
                          <span className="ml-2">via {item.extraction_method}</span>
                          {item.source_url && (
                            <a
                              href={item.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="ml-2 text-blue-600 hover:underline"
                            >
                              Source
                            </a>
                          )}
                        </div>
                        <p className="text-gray-700 text-sm">
                          {truncateContent(item.content)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Scrapy Gemini Crawl Tab */}
            {activeTab === 'scrapy' && (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Enter URL to crawl with Scrapy + Gemini
                  </label>
                  <input
                    type="url"
                    value={scrapyUrl}
                    onChange={(e) => setScrapyUrl(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="https://example.com/blog-homepage"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Max Links to Follow
                  </label>
                  <input
                    type="number"
                    value={scrapyMaxLinks}
                    onChange={(e) => setScrapyMaxLinks(parseInt(e.target.value) || 10)}
                    min="1"
                    max="50"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <button
                  onClick={handleScrapyCrawl}
                  disabled={loading}
                  className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Crawling...' : 'Run Scrapy Gemini Crawl'}
                </button>
                <p className="text-sm text-gray-600">
                  🚀 <strong>High-Performance Crawl:</strong> Uses Scrapy for fast crawling and Gemini for smart link filtering.
                </p>
                {scrapyResult && (
                  <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-md">
                    <h3 className="font-semibold text-blue-800 mb-2">
                      Scrapy Gemini Crawl Results ({scrapyResult.length} items found)
                    </h3>
                    <div className="space-y-4 max-h-96 overflow-y-auto">
                      {scrapyResult.map((item, idx) => (
                        <div key={item.url + idx} className="bg-white p-3 rounded border">
                          <div className="flex justify-between items-start mb-2">
                            <h4 className="font-medium text-gray-800 text-sm">
                              {idx + 1}. {item.title}
                            </h4>
                            <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                              {item.category}
                            </span>
                          </div>
                          <div className="text-xs text-gray-600 mb-2">
                            <a
                              href={item.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="ml-2 text-blue-600 hover:underline"
                            >
                              Source
                            </a>
                          </div>
                          <p className="text-gray-700 text-xs">
                            {truncateContent(item.content, 100)}
                          </p>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 p-3 bg-gray-50 rounded">
                      <div className="flex justify-between items-center mb-2">
                        <p className="text-sm text-gray-700">
                          <strong>JSON Output (Preview):</strong>
                        </p>
                        <button
                          onClick={() => {
                            const blob = new Blob([JSON.stringify(scrapyResult, null, 2)], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `scrapy-gemini-results-${Date.now()}.json`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }}
                          className="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700"
                        >
                          Download JSON
                        </button>
                      </div>
                      <pre className="text-xs text-gray-600 mt-1 overflow-x-auto">
{JSON.stringify(scrapyResult, null, 2)}
                      </pre>
                    </div>
                    {scrapyLogs && (
                      <div className="mt-4 p-3 bg-gray-100 rounded">
                        <h4 className="font-semibold text-gray-700 mb-2">Scrapy Logs</h4>
                        <pre className="text-xs text-gray-600 overflow-x-auto max-h-40">{scrapyLogs.stdout || ''}
{scrapyLogs.stderr || ''}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Error Display */}
            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
                <p className="text-red-800">{error}</p>
              </div>
            )}

            {/* Bulk Result Display */}
            {bulkResult && (
              <div className="mt-6 p-4 bg-purple-50 border border-purple-200 rounded-md">
                <h3 className="font-semibold text-purple-800 mb-2">
                  🎉 Bulk Scraping Complete! ({bulkResult.items.length} items found)
                </h3>
                <div className="space-y-4 max-h-96 overflow-y-auto">
                  {bulkResult.items.map((item, index) => (
                    <div key={item.id} className="bg-white p-3 rounded border">
                      <div className="flex justify-between items-start mb-2">
                        <h4 className="font-medium text-gray-800 text-sm">
                          {index + 1}. {item.title}
                        </h4>
                        <span className="bg-purple-100 text-purple-800 px-2 py-1 rounded-full text-xs">
                          {item.content_type}
                        </span>
                      </div>
                      <div className="text-xs text-gray-600 mb-2">
                        <span>{item.word_count} words</span>
                        <span className="ml-2">via {item.extraction_method}</span>
                        {item.source_url && (
                          <a
                            href={item.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="ml-2 text-blue-600 hover:underline"
                          >
                            Source
                          </a>
                        )}
                      </div>
                      <p className="text-gray-700 text-xs">
                        {truncateContent(item.content, 100)}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="mt-4 p-3 bg-gray-50 rounded">
                  <div className="flex justify-between items-center mb-2">
                    <p className="text-sm text-gray-700">
                      <strong>JSON Output Format (Preview):</strong>
                    </p>
                    <button
                      onClick={() => {
                        const fullJson = {
                          team_id: bulkResult.team_id,
                          items: bulkResult.items.map(item => ({
                            title: item.title,
                            content: item.content,
                            content_type: item.content_type,
                            source_url: item.source_url,
                            author: item.author,
                            user_id: item.user_id
                          }))
                        };
                        const blob = new Blob([JSON.stringify(fullJson, null, 2)], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `scraped-content-${bulkResult.team_id}-${Date.now()}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700"
                    >
                      Download Full JSON
                    </button>
                  </div>
                  <pre className="text-xs text-gray-600 mt-1 overflow-x-auto">
{JSON.stringify({
  team_id: bulkResult.team_id,
  items: bulkResult.items.map(item => ({
    title: item.title,
    // content: item.content.length > 200 ? item.content.substring(0, 200) + "..." : item.content,
    content: item.content,
    content_type: item.content_type,
    source_url: item.source_url,
    author: item.author,
    user_id: item.user_id
  }))
}, null, 2)}
                  </pre>
                </div>
              </div>
            )}

            {/* Single Result Display */}
            {Array.isArray(result) && result.length > 0 && (
              <div className="mt-6 p-4 bg-green-50 border border-green-200 rounded-md">
                <h3 className="font-semibold text-green-800 mb-2">
                  PDF Content Extracted and Chunked! ({result.length} sections)
                </h3>
                <div className="space-y-4 max-h-96 overflow-y-auto">
                  {result.map((item, idx) => (
                    <div key={idx} className="bg-white p-3 rounded border">
                      <div className="font-bold text-gray-800 mb-1">{item.title}</div>
                      <pre className="text-sm text-gray-700 whitespace-pre-wrap">
                        {truncateContent(item.content, 500)}
                      </pre>
                    </div>
                  ))}
                </div>
                {/* JSON Output Preview for PDF */}
                <div className="mt-4 p-3 bg-gray-50 rounded">
                  <div className="flex justify-between items-center mb-2">
                    <p className="text-sm text-gray-700">
                      <strong>JSON Output Format (Preview):</strong>
                    </p>
                    <button
                      onClick={() => {
                        const fullJson = {
                          items: result.map(item => ({
                            title: item.title,
                            content: item.content,
                            content_type: item.content_type,
                            source_url: item.source_url,
                            author: item.author,
                            user_id: item.user_id
                          }))
                        };
                        const blob = new Blob([JSON.stringify(fullJson, null, 2)], { type: 'application/json' });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `pdf-chunks-${Date.now()}.json`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="bg-blue-600 text-white px-3 py-1 rounded text-xs hover:bg-blue-700"
                    >
                      Download Full JSON
                    </button>
                  </div>
                  <pre className="text-xs text-gray-600 mt-1 overflow-x-auto">
{JSON.stringify({
  items: result.map(item => ({
    title: item.title,
    content: item.content,
    content_type: item.content_type,
    source_url: item.source_url,
    author: item.author,
    user_id: item.user_id
  }))
}, null, 2)}
                  </pre>
                </div>
              </div>
            )}
            {/* Show message if no content extracted */}
            {Array.isArray(result) && result.length === 0 && (
              <div className="mt-6 p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                <p className="text-yellow-800">No content could be extracted from this PDF.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default App;