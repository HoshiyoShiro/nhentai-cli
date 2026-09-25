#!/usr/bin/env python3
"""
NHentai Scraper - Alternative to API when Cloudflare/404 issues occur
Parses HTML directly from nhentai.net pages
"""

import re
import json
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup


@dataclass
class GalleryDataScraped:
    """Gallery data scraped from HTML"""
    id: int
    media_id: int
    title: Dict[str, str]
    page_count: int
    language: Optional[str] = None
    tags: List[Dict[str, Any]] = field(default_factory=list)
    cover_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    page_urls: List[str] = field(default_factory=list)

    @property
    def english_title(self) -> str:
        return self.title.get('english', '') or self.title.get('pretty', '')

    @property
    def japanese_title(self) -> str:
        return self.title.get('japanese', '')


class NHentaiScraper:
    """Scraper for nhentai.net that parses HTML instead of using API"""

    BASE_URL = "https://nhentai.net"

    def __init__(self, delay: float = 1.0, cookie_file: Optional[str] = None):
        self.delay = delay
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://nhentai.net/',
            'Connection': 'keep-alive',
        })

        if cookie_file:
            self._load_cookies(cookie_file)

        self._last_request_time = 0

    def _load_cookies(self, filepath: str):
        """Load cookies from JSON file"""
        try:
            with open(filepath, 'r') as f:
                cookies = json.load(f)

            if isinstance(cookies, dict):
                self._session.cookies.update(cookies)
            print(f"Loaded cookies from {filepath}")
        except Exception as e:
            print(f"Warning: Could not load cookies: {e}")

    def _rate_limit(self):
        """Rate limiting"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def get_gallery(self, gallery_id: int) -> Optional[GalleryDataScraped]:
        """Scrape gallery data from HTML page"""
        self._rate_limit()

        url = f"{self.BASE_URL}/g/{gallery_id}/"

        try:
            response = self._session.get(url, timeout=30)

            if response.status_code == 404:
                print(f"Gallery {gallery_id} not found (404)")
                return None

            response.raise_for_status()

            return self._parse_gallery_page(response.text, gallery_id)

        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e}")
            return None
        except Exception as e:
            print(f"Error fetching gallery: {e}")
            return None

    def _parse_gallery_page(self, html: str, gallery_id: int) -> GalleryDataScraped:
        """Parse gallery HTML page"""
        soup = BeautifulSoup(html, 'html.parser')

        # Method 1: Look for JSON data in script tags
        # nhentai stores gallery data in window._gallery
        data = None

        for script in soup.find_all('script'):
            if not script.string:
                continue

            # Look for window._gallery = JSON.parse("...")
            match = re.search(r'window\._gallery\s*=\s*JSON\.parse\("(.+?)"\)', script.string)
            if match:
                try:
                    json_str = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
                    data = json.loads(json_str)
                    break
                except:
                    pass

            # Alternative: window._gallery = {...}
            match = re.search(r'window\._gallery\s*=\s*(\{.*?\});', script.string, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    break
                except:
                    pass

        if data:
            return self._parse_json_data(data, gallery_id)

        # Fallback: parse from HTML structure
        return self._parse_html_fallback(soup, gallery_id)

    def _parse_json_data(self, data: Dict, gallery_id: int) -> GalleryDataScraped:
        """Parse gallery from JSON data"""
        title = {
            'english': data.get('title', {}).get('english', ''),
            'japanese': data.get('title', {}).get('japanese', ''),
            'pretty': data.get('title', {}).get('pretty', '')
        }

        media_id = int(data.get('media_id', 0))

        # Extract tags
        tags = []
        for tag_data in data.get('tags', []):
            tags.append({
                'id': tag_data.get('id', 0),
                'name': tag_data.get('name', ''),
                'type': tag_data.get('type', 'tag'),
                'count': tag_data.get('count', 0)
            })

        # Detect language
        language = None
        for tag in tags:
            if tag['type'] == 'language':
                language = tag['name']
                break

        # Generate page URLs
        page_count = data.get('num_pages', 0)
        page_urls = []
        images = data.get('images', {})
        pages = images.get('pages', [])

        ext_map = {'j': 'jpg', 'p': 'png', 'g': 'gif', 'w': 'webp'}

        for i, page in enumerate(pages, 1):
            ext = page.get('t', 'j')
            extension = ext_map.get(ext, 'jpg')
            page_urls.append(f"https://i1.nhentai.net/galleries/{media_id}/{i}.{extension}")

        # Cover and thumbnail
        cover_url = None
        thumbnail_url = None
        if 'cover' in images:
            cover_ext = images['cover'].get('t', 'j')
            cover_ext = ext_map.get(cover_ext, 'jpg')
            cover_url = f"https://i1.nhentai.net/galleries/{media_id}/cover.{cover_ext}"
            thumbnail_url = f"https://t1.nhentai.net/galleries/{media_id}/thumb.{cover_ext}"

        return GalleryDataScraped(
            id=gallery_id,
            media_id=media_id,
            title=title,
            page_count=page_count,
            language=language,
            tags=tags,
            cover_url=cover_url,
            thumbnail_url=thumbnail_url,
            page_urls=page_urls
        )

    def _parse_html_fallback(self, soup: BeautifulSoup, gallery_id: int) -> GalleryDataScraped:
        """Fallback parsing if JSON data not found"""
        # Get title
        title_tag = soup.find('h1') or soup.find('h2')
        title_text = title_tag.get_text(strip=True) if title_tag else str(gallery_id)

        title = {
            'english': title_text,
            'japanese': '',
            'pretty': title_text
        }

        # Count pages from thumbnail images
        thumbs = soup.find_all('a', class_='gallerythumb')
        page_count = len(thumbs)

        # Extract tags
        tags = []
        tag_sections = soup.find_all('div', class_='tag-container')
        for section in tag_sections:
            tag_type_elem = section.find('span', class_='name')
            if tag_type_elem:
                tag_type = tag_type_elem.get_text(strip=True).lower()
                tag_links = section.find_all('a', class_='tag')
                for tag_link in tag_links:
                    tag_name = tag_link.get_text(strip=True)
                    tags.append({
                        'id': 0,
                        'name': tag_name,
                        'type': tag_type,
                        'count': 0
                    })

        # Detect language
        language = None
        for tag in tags:
            if tag['type'] == 'language':
                language = tag['name']
                break

        # Get cover image
        cover_img = soup.find('div', id='cover')
        cover_url = None
        if cover_img:
            img = cover_img.find('img')
            if img:
                cover_url = img.get('data-src') or img.get('src')

        return GalleryDataScraped(
            id=gallery_id,
            media_id=0,
            title=title,
            page_count=page_count,
            language=language,
            tags=tags,
            cover_url=cover_url,
            page_urls=[]
        )

    def search(self, query: str = "", page: int = 1) -> List[Dict[str, Any]]:
        """Search galleries by query"""
        self._rate_limit()

        url = f"{self.BASE_URL}/search/"
        params = {'q': query, 'page': page}

        try:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()

            return self._parse_search_page(response.text)

        except Exception as e:
            print(f"Search error: {e}")
            return []

    def _parse_search_page(self, html: str) -> List[Dict[str, Any]]:
        """Parse search results page"""
        soup = BeautifulSoup(html, 'html.parser')
        results = []

        galleries = soup.find_all('div', class_='gallery')

        for gallery in galleries:
            link = gallery.find('a', class_='cover')
            if not link:
                continue

            href = link.get('href', '')
            gallery_id = int(href.strip('/').split('/')[-1]) if href else 0

            caption = gallery.find('div', 'caption')
            title = caption.get_text(strip=True) if caption else ''

            img = link.find('img')
            thumbnail = ''
            if img:
                thumbnail = img.get('data-src') or img.get('src', '')

            results.append({
                'id': gallery_id,
                'title': title,
                'thumbnail': thumbnail,
                'url': f"{self.BASE_URL}{href}"
            })

        return results


if __name__ == "__main__":
    import sys

    cookie_file = sys.argv[1] if len(sys.argv) > 1 else None
    scraper = NHentaiScraper(delay=1.0, cookie_file=cookie_file)

    # Test with gallery ID
    test_id = 574323
    print(f"Testing gallery {test_id}...")

    gallery = scraper.get_gallery(test_id)
    if gallery:
        print(f"Success!")
        print(f"Title: {gallery.english_title}")
        print(f"Pages: {gallery.page_count}")
        print(f"Tags: {len(gallery.tags)}")
        if gallery.page_urls:
            print(f"First page: {gallery.page_urls[0]}")
    else:
        print("Failed to get gallery")
