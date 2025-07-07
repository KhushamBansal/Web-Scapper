#!/usr/bin/env python3
import requests
import json
import time
import sys
from urllib.parse import urljoin

# Get the backend URL from the frontend .env file
with open('/app/frontend/.env', 'r') as f:
    for line in f:
        if line.startswith('REACT_APP_BACKEND_URL='):
            BACKEND_URL = line.strip().split('=')[1].strip('"\'')
            break

# Ensure the URL doesn't have quotes
BACKEND_URL = BACKEND_URL.strip('"\'')
API_URL = urljoin(BACKEND_URL, '/api')

# Test parameters - using the user-specified team_id
TEAM_ID = "aline123"
USER_ID = "test-user-456"

# Test URLs
TEST_URLS = [
    "https://www.python.org/about/",  # Simple website
    "https://fastapi.tiangolo.com/tutorial/",  # Technical documentation
    "https://martinfowler.com/articles/patterns-of-distributed-systems/leader-follower.html"  # Technical blog
]

# Test URLs for bulk scraping (pages with multiple links)
BULK_TEST_URLS = [
    "https://www.python.org/blogs/",  # Blog homepage with multiple article links
    "https://fastapi.tiangolo.com/",  # Technical documentation with multiple links
    "https://dev.to/",  # Developer blog site with many articles
]

def test_root_endpoint():
    """Test the basic API endpoint GET /api/"""
    print("\n=== Testing Root Endpoint ===")
    try:
        response = requests.get(f"{API_URL}/")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200
        assert "message" in response.json()
        print("✅ Root endpoint test passed")
        return True
    except Exception as e:
        print(f"❌ Root endpoint test failed: {str(e)}")
        return False

def test_status_endpoints():
    """Test the status endpoints GET and POST /api/status"""
    print("\n=== Testing Status Endpoints ===")
    try:
        # Test POST /api/status
        post_data = {"client_name": "Backend Test Client"}
        post_response = requests.post(f"{API_URL}/status", json=post_data)
        print(f"POST Status Code: {post_response.status_code}")
        print(f"POST Response: {post_response.json()}")
        
        assert post_response.status_code == 200
        assert "id" in post_response.json()
        assert post_response.json()["client_name"] == "Backend Test Client"
        
        # Test GET /api/status
        get_response = requests.get(f"{API_URL}/status")
        print(f"GET Status Code: {get_response.status_code}")
        print(f"GET Response: {get_response.json()[:2] if len(get_response.json()) > 2 else get_response.json()}")
        
        assert get_response.status_code == 200
        assert isinstance(get_response.json(), list)
        
        print("✅ Status endpoints test passed")
        return True
    except Exception as e:
        print(f"❌ Status endpoints test failed: {str(e)}")
        return False

def test_scrape_url_endpoint():
    """Test the URL scraping endpoint POST /api/scrape-url"""
    print("\n=== Testing URL Scraping Endpoint ===")
    
    all_passed = True
    
    for url in TEST_URLS:
        try:
            print(f"\nTesting URL: {url}")
            post_data = {
                "url": url,
                "team_id": TEAM_ID,
                "user_id": USER_ID,
                "content_type": "blog"
            }
            
            response = requests.post(f"{API_URL}/scrape-url", json=post_data, timeout=60)
            print(f"Status Code: {response.status_code}")
            
            result = response.json()
            print(f"Success: {result.get('success')}")
            print(f"Message: {result.get('message')}")
            
            if result.get('data'):
                print(f"Title: {result['data'].get('title')}")
                print(f"Word Count: {result['data'].get('word_count')}")
                print(f"Extraction Method: {result['data'].get('extraction_method')}")
                content_preview = result['data'].get('content', '')[:150] + "..." if result['data'].get('content') else "No content"
                print(f"Content Preview: {content_preview}")
            
            assert response.status_code == 200
            assert result.get('success') is True
            assert result.get('data') is not None
            assert result['data'].get('title') is not None
            assert result['data'].get('content') is not None
            assert result['data'].get('word_count') > 0
            assert result['data'].get('extraction_method') in ["newspaper3k", "trafilatura", "readability"]
            
            print(f"✅ URL scraping test passed for {url}")
        except Exception as e:
            print(f"❌ URL scraping test failed for {url}: {str(e)}")
            all_passed = False
    
    return all_passed

def test_knowledge_base_endpoint():
    """Test the knowledge base retrieval endpoint GET /api/knowledge-base"""
    print("\n=== Testing Knowledge Base Endpoint ===")
    try:
        # Test with team_id only
        team_response = requests.get(f"{API_URL}/knowledge-base?team_id={TEAM_ID}")
        print(f"Team-only Status Code: {team_response.status_code}")
        print(f"Team-only Response Length: {len(team_response.json())}")
        if team_response.json():
            print(f"First item title: {team_response.json()[0].get('title')}")
        
        assert team_response.status_code == 200
        assert isinstance(team_response.json(), list)
        
        # Test with team_id and user_id
        user_response = requests.get(f"{API_URL}/knowledge-base?team_id={TEAM_ID}&user_id={USER_ID}")
        print(f"Team+User Status Code: {user_response.status_code}")
        print(f"Team+User Response Length: {len(user_response.json())}")
        
        assert user_response.status_code == 200
        assert isinstance(user_response.json(), list)
        
        print("✅ Knowledge base endpoint test passed")
        return True
    except Exception as e:
        print(f"❌ Knowledge base endpoint test failed: {str(e)}")
        return False

def test_bulk_scrape_endpoint():
    """Test the bulk scraping endpoint POST /api/bulk-scrape"""
    print("\n=== Testing Bulk Scraping Endpoint ===")
    
    all_passed = True
    
    for url in BULK_TEST_URLS:
        try:
            print(f"\nTesting Bulk Scrape URL: {url}")
            
            # Test with different max_links values
            for max_links in [3, 5]:
                print(f"Testing with max_links={max_links}")
                post_data = {
                    "url": url,
                    "team_id": TEAM_ID,
                    "user_id": USER_ID,
                    "max_depth": 1,
                    "max_links": max_links,
                    "include_base_url": True
                }
                
                response = requests.post(f"{API_URL}/bulk-scrape", json=post_data, timeout=120)
                print(f"Status Code: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"Error response: {response.text}")
                    all_passed = False
                    continue
                
                result = response.json()
                print(f"Team ID: {result.get('team_id')}")
                print(f"Number of items scraped: {len(result.get('items', []))}")
                
                # Print details of first few items
                for i, item in enumerate(result.get('items', [])[:2]):
                    print(f"Item {i+1}:")
                    print(f"  Title: {item.get('title')}")
                    print(f"  Source URL: {item.get('source_url')}")
                    print(f"  Word Count: {item.get('word_count')}")
                    content_preview = item.get('content', '')[:100] + "..." if item.get('content') else "No content"
                    print(f"  Content Preview: {content_preview}")
                
                # Assertions
                assert response.status_code == 200
                assert result.get('team_id') == TEAM_ID
                assert isinstance(result.get('items'), list)
                
                # Check if we got any items
                if len(result.get('items', [])) == 0:
                    print(f"⚠️ Warning: No items were scraped from {url}")
                    continue
                
                # Check if we got at most max_links items
                assert len(result.get('items', [])) <= max_links + 1  # +1 for the base URL if included
                
                # Check item structure
                for item in result.get('items', []):
                    assert 'title' in item
                    assert 'content' in item
                    assert 'content_type' in item
                    assert 'source_url' in item
                    assert 'user_id' in item
                    assert item.get('user_id') == USER_ID
                    assert item.get('team_id') == TEAM_ID
                
                print(f"✅ Bulk scraping test passed for {url} with max_links={max_links}")
            
        except Exception as e:
            print(f"❌ Bulk scraping test failed for {url}: {str(e)}")
            all_passed = False
    
    # Test error handling with invalid URL
    try:
        print("\nTesting with invalid URL")
        post_data = {
            "url": "https://nonexistentwebsite123456789.com",
            "team_id": TEAM_ID,
            "user_id": USER_ID,
            "max_depth": 1,
            "max_links": 5,
            "include_base_url": True
        }
        
        response = requests.post(f"{API_URL}/bulk-scrape", json=post_data, timeout=30)
        print(f"Invalid URL Status Code: {response.status_code}")
        
        # The API is returning 200 even for invalid URLs, but should have empty items
        if response.status_code == 200:
            result = response.json()
            print(f"Number of items scraped: {len(result.get('items', []))}")
            # For invalid URLs, we should get 0 items or an error
            assert len(result.get('items', [])) == 0 or 'error' in result
            print("✅ Invalid URL handling test passed (returns 200 with empty items)")
        else:
            # We expect either a 400 or 500 error for invalid URL
            assert response.status_code in [400, 500]
            print("✅ Invalid URL error handling test passed (returns error code)")
    except Exception as e:
        print(f"❌ Invalid URL error handling test failed: {str(e)}")
        all_passed = False
    
    return all_passed

def run_all_tests():
    """Run all tests and return overall status"""
    print(f"Testing backend API at: {API_URL}")
    
    test_results = {
        "root_endpoint": test_root_endpoint(),
        "status_endpoints": test_status_endpoints(),
        "scrape_url_endpoint": test_scrape_url_endpoint(),
        "knowledge_base_endpoint": test_knowledge_base_endpoint(),
        "bulk_scrape_endpoint": test_bulk_scrape_endpoint()
    }
    
    print("\n=== Test Summary ===")
    for test_name, result in test_results.items():
        print(f"{test_name}: {'✅ PASSED' if result else '❌ FAILED'}")
    
    all_passed = all(test_results.values())
    print(f"\nOverall Test Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return all_passed

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)