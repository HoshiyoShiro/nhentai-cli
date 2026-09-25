"""
NHentai API Client (v2)
Based on NClientV3 architecture - Python implementation
Supports manual cookie injection for Cloudflare bypass
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import requests


RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
RETRY_DELAYS = (5, 15)


def request_with_retry(
    session: requests.Session, method: str, url: str, **kwargs
) -> requests.Response:
    """Send a request, retrying timeouts, connection errors and 429/5xx responses."""
    kwargs.setdefault('timeout', 30)
    for attempt, delay in enumerate((*RETRY_DELAYS, None), 1):
        try:
            response = session.request(method, url, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if delay is None:
                raise
            reason = type(e).__name__
        else:
            if response.status_code not in RETRY_STATUS_CODES or delay is None:
                return response
            reason = f"HTTP {response.status_code}"
            retry_after = response.headers.get('Retry-After', '')
            if retry_after.isdigit():
                delay = max(delay, min(int(retry_after), 120))
            response.close()
        print(f"Request failed ({reason}), retrying in {delay}s "
              f"(attempt {attempt + 1}/{len(RETRY_DELAYS) + 1})...")
        time.sleep(delay)


def _image_extension(data: Dict[str, Any]) -> str:
    """Translate the API's compact image-type code to a file extension."""
    return {
        'j': 'jpg', 'p': 'png', 'g': 'gif', 'w': 'webp', 'a': 'avif',
    }.get(data.get('t', 'j'), 'jpg')


def _cdn_url(server: str, path: str) -> str:
    """Join an API-provided CDN server and relative media path."""
    return f"{server.rstrip('/')}/{path.lstrip('/')}"


def _load_project_api_key() -> Optional[str]:
    """Load NHENTAI_API_KEY from the environment, or a .env file in the
    current directory or the project root."""
    configured = os.environ.get('NHENTAI_API_KEY')
    if configured:
        return configured

    env_files = [
        os.path.join(os.getcwd(), '.env'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
    ]
    for env_file in env_files:
        try:
            with open(env_file, encoding='utf-8') as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    name, value = line.split('=', 1)
                    if name.strip() == 'NHENTAI_API_KEY':
                        value = value.strip()
                        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                            value = value[1:-1]
                        if value:
                            return value
        except FileNotFoundError:
            continue
    return None


class ApiRequestType(Enum):
    """Enum for API request types matching NClientV3"""
    BYALL = "galleries"
    BYTAG = "search"
    BYSEARCH = "search"
    BYSINGLE = "galleries"
    RELATED = "related"
    FAVORITE = "favorites"
    RANDOM = "galleries/random"
    RANDOM_FAVORITE = "favorites/random"


class TagType(Enum):
    """Tag types from NClientV3"""
    TAG = "tag"
    CATEGORY = "category"
    ARTIST = "artist"
    PARODY = "parody"
    CHARACTER = "character"
    GROUP = "group"
    LANGUAGE = "language"


class TagStatus(Enum):
    """Tag status for filtering"""
    DEFAULT = "default"
    ACCEPTED = "accepted"
    AVOIDED = "avoided"


@dataclass
class Tag:
    """Represents a gallery tag"""
    id: int
    name: str
    type: TagType
    count: int = 0
    status: TagStatus = TagStatus.DEFAULT

    def to_query_tag(self) -> str:
        """Convert tag to query format"""
        base = f"{self.type.value}:{self.name.replace(' ', '+')}"
        if self.status == TagStatus.AVOIDED:
            return f"-{base}"
        return base

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'Tag':
        """Parse tag from JSON response"""
        return cls(
            id=data.get('id', 0),
            name=data.get('name', ''),
            # The API occasionally adds tag types.  Treat unknown values as
            # ordinary tags instead of failing an otherwise valid gallery.
            type=TagType._value2member_map_.get(data.get('type'), TagType.TAG),
            count=data.get('count', 0)
        )


@dataclass
class Page:
    """Represents a gallery page/image"""
    page_number: int
    image_url: str
    thumbnail_url: str
    width: int = 0
    height: int = 0
    extension: str = "jpg"

    @classmethod
    def from_json(
        cls,
        data: Dict[str, Any],
        page_num: int,
        media_id: int,
        host: str = "nhentai.net",
        filename: Optional[str] = None,
        thumbnail: bool = False,
    ) -> 'Page':
        """Parse page from JSON and construct URLs"""
        extension = _image_extension(data)

        filename = filename or f"{page_num}.{extension}"
        path = f"galleries/{media_id}/{filename}"
        image_host = f"i1.{host}"
        thumbnail_host = f"t1.{host}"

        return cls(
            page_number=page_num,
            image_url=f"https://{thumbnail_host if thumbnail else image_host}/{path}",
            thumbnail_url=f"https://{thumbnail_host}/{path}",
            width=data.get('w', 0),
            height=data.get('h', 0),
            extension=extension
        )

    @classmethod
    def from_v2(cls, data: Dict[str, Any], image_server: str, thumb_server: str) -> 'Page':
        """Parse a v2 page using the CDN paths returned by the API."""
        path = data.get('path', '')
        thumbnail_path = data.get('thumbnail', path)
        return cls(
            page_number=data.get('number', 0),
            image_url=_cdn_url(image_server, path),
            thumbnail_url=_cdn_url(thumb_server, thumbnail_path),
            width=data.get('width', 0),
            height=data.get('height', 0),
            extension=path.rsplit('.', 1)[-1] if '.' in path else 'jpg',
        )


@dataclass
class GalleryData:
    """Complete gallery metadata"""
    id: int
    media_id: int
    title: Dict[str, str]
    pages: List[Page] = field(default_factory=list)
    cover: Optional[Page] = None
    thumbnail: Optional[Page] = None
    tags: List[Tag] = field(default_factory=list)
    upload_date: Optional[int] = None
    favorite_count: int = 0
    page_count: int = 0
    language: Optional[str] = None

    @property
    def english_title(self) -> str:
        return self.title.get('english', '') or self.title.get('pretty', '')

    @property
    def japanese_title(self) -> str:
        return self.title.get('japanese', '')

    @classmethod
    def from_json(
        cls, data: Dict[str, Any], host: str = "nhentai.net",
        image_server: Optional[str] = None, thumb_server: Optional[str] = None,
    ) -> 'GalleryData':
        """Parse full gallery from JSON response"""
        media_id = int(data.get('media_id', 0))
        if image_server and thumb_server and 'pages' in data:
            pages = [Page.from_v2(page, image_server, thumb_server)
                     for page in data.get('pages', [])]
            cover_data = data.get('cover')
            thumbnail_data = data.get('thumbnail')
            cover = Page.from_v2(
                {'number': 0, **cover_data, 'thumbnail': cover_data.get('path', '')},
                image_server, thumb_server,
            ) if cover_data else None
            thumbnail = Page.from_v2(
                {'number': 0, **thumbnail_data, 'thumbnail': thumbnail_data.get('path', '')},
                image_server, thumb_server,
            ) if thumbnail_data else None
            tags = [Tag.from_json(t) for t in data.get('tags', [])]
            language = next((tag.name for tag in tags if tag.type == TagType.LANGUAGE), None)
            return cls(
                id=data.get('id', 0), media_id=media_id, title=data.get('title', {}),
                pages=pages, cover=cover, thumbnail=thumbnail, tags=tags,
                upload_date=data.get('upload_date'),
                favorite_count=data.get('num_favorites', 0),
                page_count=data.get('num_pages', len(pages)), language=language,
            )

        pages = []
        images = data.get('images', {})
        pages_data = images.get('pages', [])
        for i, page_data in enumerate(pages_data, 1):
            pages.append(Page.from_json(page_data, i, media_id, host))

        cover = None
        if 'cover' in images:
            cover_ext = _image_extension(images['cover'])
            cover = Page.from_json(
                images['cover'], 1, media_id, host,
                filename=f"cover.{cover_ext}",
            )

        thumbnail = None
        if 'thumbnail' in images:
            thumb_ext = _image_extension(images['thumbnail'])
            thumbnail = Page.from_json(
                images['thumbnail'], 1, media_id, host,
                filename=f"thumb.{thumb_ext}", thumbnail=True,
            )

        tags = [Tag.from_json(t) for t in data.get('tags', [])]

        language = None
        for tag in tags:
            if tag.type == TagType.LANGUAGE:
                language = tag.name
                break

        return cls(
            id=data.get('id', 0),
            media_id=media_id,
            title=data.get('title', {}),
            pages=pages,
            cover=cover,
            thumbnail=thumbnail,
            tags=tags,
            upload_date=data.get('upload_date'),
            favorite_count=data.get('num_favorites', 0),
            page_count=data.get('num_pages', 0),
            language=language
        )


@dataclass
class SimpleGallery:
    """Lightweight gallery for search results"""
    id: int
    media_id: int
    title: str
    thumbnail_url: str
    language: Optional[str] = None
    tags: List[Tag] = field(default_factory=list)
    tag_ids: List[int] = field(default_factory=list)
    page_count: int = 0

    @classmethod
    def from_v2_list_item(
        cls, data: Dict[str, Any], host: str = "nhentai.net",
        thumb_server: Optional[str] = None,
    ) -> 'SimpleGallery':
        """Parse from v2 API list item"""
        title_obj = data.get('title', {})
        title = (data.get('english_title') or title_obj.get('english') or
                 title_obj.get('pretty') or data.get('japanese_title') or
                 title_obj.get('japanese', ''))

        media_id = int(data.get('media_id', 0))
        thumbnail_data = data.get('images', {}).get('thumbnail', {})
        thumb_path = data.get('thumbnail') or f"galleries/{media_id}/thumb.{_image_extension(thumbnail_data)}"
        thumbnail_url = (_cdn_url(thumb_server, thumb_path) if thumb_server
                         else f"https://t1.{host}/{thumb_path}")

        tags = []
        if 'tags' in data:
            tags = [Tag.from_json(t) for t in data['tags']]

        language = None
        for tag in tags:
            if tag.type == TagType.LANGUAGE:
                language = tag.name
                break

        return cls(
            id=data.get('id', 0),
            media_id=media_id,
            title=title,
            thumbnail_url=thumbnail_url,
            language=language,
            tags=tags,
            tag_ids=data.get('tag_ids', []),
            page_count=data.get('num_pages', 0)
        )


class NHentaiAPI:
    """Main API client for NHentai with cookie support"""

    BASE_HOST = "nhentai.net"
    API_VERSION = "api/v2"

    def __init__(
        self, 
        host: Optional[str] = None, 
        delay: float = 0.5,
        cookies: Optional[Dict[str, str]] = None,
        cookie_file: Optional[str] = None,
        user_agent: Optional[str] = None,
        api_key: Optional[str] = None,
        debug: bool = False
    ):
        """
        Initialize API client

        Args:
            host: Mirror host (default: nhentai.net)
            delay: Delay between requests in seconds
            cookies: Dictionary of cookies (e.g., {'cf_clearance': 'xxx'})
            cookie_file: Path to JSON file containing cookies
            user_agent: Browser User-Agent associated with the session cookie
            api_key: API key; defaults to NHENTAI_API_KEY from the environment or .env
            debug: Enable debug output
        """
        self.host = host or self.BASE_HOST
        self.delay = delay
        self.debug = debug
        self._last_request_time = 0
        self._cdn_servers: Optional[Tuple[str, str]] = None
        self._session = requests.Session()

        # Use headers that requests can actually decode.  Advertising Brotli
        # without a Brotli decoder can turn an otherwise valid JSON response
        # into a JSONDecodeError.
        self._session.headers.update({
            'User-Agent': user_agent or 'nhentai-cli/1.0 (local command-line client)',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://nhentai.net/',
            'Connection': 'keep-alive',
        })
        api_key = api_key or _load_project_api_key()
        if api_key:
            self._session.headers['Authorization'] = f'Key {api_key}'

        # Load cookies from file if provided
        if cookie_file:
            self._load_cookies_from_file(cookie_file)

        # Add provided cookies
        if cookies:
            self._session.cookies.update(cookies)
            if self.debug:
                print(f"Added cookies: {list(cookies.keys())}")

    def _load_cookies_from_file(self, filepath: str):
        """Load cookies from JSON file"""
        try:
            with open(filepath, 'r') as f:
                cookie_data = json.load(f)

            # Handle different cookie formats
            if isinstance(cookie_data, dict):
                # Simple dict format: {"name": "value"}
                self._session.cookies.update(cookie_data)
                if self.debug:
                    print(f"Loaded {len(cookie_data)} cookies from dict")
            elif isinstance(cookie_data, list):
                # Browser export format: [{"name": "x", "value": "y", ...}]
                for cookie in cookie_data:
                    if 'name' in cookie and 'value' in cookie:
                        self._session.cookies.set(
                            cookie['name'], 
                            cookie['value'],
                            domain=cookie.get('domain', '.nhentai.net'),
                            path=cookie.get('path', '/')
                        )
                if self.debug:
                    print(f"Loaded {len(cookie_data)} cookies from list")

            print(f"Loaded cookies from {filepath}")
            if self.debug:
                print(f"Session cookie names: {list(self._session.cookies.keys())}")

        except Exception as e:
            print(f"Warning: Could not load cookies from {filepath}: {e}")

    def save_cookies(self, filepath: str):
        """Save current cookies to JSON file"""
        cookies = []
        for cookie in self._session.cookies:
            cookies.append({
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path
            })

        with open(filepath, 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"Saved cookies to {filepath}")

    def _get_base_url(self) -> str:
        return f"https://{self.host}/"

    def _get_api_url(self) -> str:
        return f"{self._get_base_url()}{self.API_VERSION}/"

    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP GET request to API"""
        self._rate_limit()

        url = f"{self._get_api_url()}{endpoint}"

        if self.debug:
            print(f"Requesting: {url}")
            print(f"Cookies present: {list(self._session.cookies.keys())}")

        try:
            response = request_with_retry(self._session, 'GET', url, params=params)

            if self.debug:
                print(f"Status: {response.status_code}")
                print(f"Response: {response.text[:500]}")

            # Handle 404 - gallery not found
            if response.status_code == 404:
                raise Exception(f"Gallery not found (404)")

            # Handle Cloudflare challenge
            if response.status_code == 403 or "cf-browser-verification" in response.text:
                raise Exception(f"Cloudflare blocked the request. Try getting fresh cookies.")

            response.raise_for_status()
            return response.json()
        except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
            content_type = response.headers.get('Content-Type', 'unknown')
            raise Exception(
                "Invalid JSON response "
                f"(HTTP {response.status_code}, Content-Type: {content_type}). "
                "Possibly blocked by Cloudflare."
            )
        except Exception as e:
            if "API request failed" not in str(e):
                raise Exception(f"API request failed: {e}")
            raise

    def _make_post_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an authenticated API POST request and decode its JSON body."""
        self._rate_limit()
        url = f"{self._get_api_url()}{endpoint}"
        try:
            response = request_with_retry(self._session, 'POST', url, params=params)
            if response.status_code == 401:
                raise Exception("This endpoint requires a valid API key in NHENTAI_API_KEY")
            response.raise_for_status()
            return response.json()
        except json.JSONDecodeError:
            raise Exception("API returned an invalid JSON response")
        except Exception as e:
            if "API request failed" not in str(e):
                raise Exception(f"API request failed: {e}")
            raise

    def _get_gallery_api(self, gallery_id: int) -> GalleryData:
        """Fetch and parse a single gallery from the v2 API."""
        if not isinstance(gallery_id, int) or gallery_id <= 0:
            raise ValueError("Gallery ID must be a positive integer")

        data = self._make_request(f"galleries/{gallery_id}")
        image_server, thumb_server = self._get_cdn_servers()
        return GalleryData.from_json(
            data, host=self.host, image_server=image_server, thumb_server=thumb_server,
        )

    def _get_cdn_servers(self) -> Tuple[str, str]:
        """Get the active CDN hosts; never guess media URL patterns."""
        if self._cdn_servers is None:
            data = self._make_request("cdn")
            image_servers = data.get('image_servers', [])
            thumb_servers = data.get('thumb_servers', [])
            if not image_servers or not thumb_servers:
                raise Exception("API did not return usable CDN servers")
            self._cdn_servers = (image_servers[0], thumb_servers[0])
        return self._cdn_servers

    def search(
        self, 
        query: str = "", 
        tags: Optional[List[Tag]] = None,
        page: int = 1,
        sort: str = "date"
    ) -> List[SimpleGallery]:
        """Search galleries by query and/or tags"""
        query_parts = []

        if query:
            query_parts.append(query)

        if tags:
            for tag in tags:
                query_parts.append(tag.to_query_tag())

        final_query = " ".join(query_parts) if query_parts else ""

        params = {
            "page": page,
            "sort": sort
        }

        if final_query:
            params["query"] = final_query

        data = self._make_request("search", params)

        results = data.get('result', [])
        _, thumb_server = self._get_cdn_servers()
        return [SimpleGallery.from_v2_list_item(item, host=self.host, thumb_server=thumb_server)
                for item in results]

    def get_gallery(self, gallery_id: int) -> GalleryData:
        """Fetch a gallery by its numeric ID."""
        return self._get_gallery_api(gallery_id)

    def get_random(self) -> GalleryData:
        """Fetch a random gallery"""
        data = self._make_request("galleries/random")

        if 'id' in data and 'title' not in data:
            return self.get_gallery(data['id'])

        return self.get_gallery(data['id']) if 'id' in data else GalleryData.from_json(data, host=self.host)

    def get_download_url(self, gallery_id: int, archive_format: str = "zip") -> str:
        """Request the API-issued, short-lived archive URL for a gallery."""
        if archive_format not in {"zip", "cbz", "torrent"}:
            raise ValueError("Archive format must be zip, cbz, or torrent")
        data = self._make_post_request(
            f"galleries/{gallery_id}/download", {"format": archive_format},
        )
        if not data.get("url"):
            raise Exception("API did not return a download URL")
        return data["url"]

    def browse_all(self, page: int = 1) -> List[SimpleGallery]:
        """Browse all galleries (main page)"""
        params = {"page": page}
        data = self._make_request("galleries", params)

        results = data.get('result', [])
        _, thumb_server = self._get_cdn_servers()
        return [SimpleGallery.from_v2_list_item(item, host=self.host, thumb_server=thumb_server)
                for item in results]

    def search_by_code(self, code: str) -> Optional[GalleryData]:
        """Look up a gallery code, returning ``None`` only for invalid input."""
        try:
            gallery_id = int(code)
        except (TypeError, ValueError):
            return None
        if gallery_id <= 0:
            return None
        return self.get_gallery(gallery_id)
