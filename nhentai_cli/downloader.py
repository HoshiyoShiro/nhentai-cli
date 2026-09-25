"""
Gallery Downloader and PDF Converter
Handles downloading images and converting to PDF/ZIP
"""

import os
import re
import time
import zipfile
import requests
from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass
from io import BytesIO
from PIL import Image
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from .api_client import (
    GalleryData, Page, SimpleGallery, NHentaiAPI, RETRY_DELAYS, request_with_retry,
)


def _natural_sort_key(path: Path):
    """Sort key so '2.webp' comes before '10.webp'"""
    parts = re.split(r'(\d+)', str(path.relative_to(path.anchor)).lower())
    return [int(p) if p.isdigit() else p for p in parts]


def _sanitize_filename(name: str, parent: Path) -> str:
    """Sanitize filename and keep full paths under the Windows 260-char limit"""
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Leave room for the parent path plus files created inside a gallery
    # folder (e.g. "\.metadata.json", ".DUP1", extracted page names).
    max_len = min(200, 259 - len(str(parent.resolve())) - 1 - 40)
    name = name[:max(max_len, 20)]
    return name.rstrip('. ').strip()


@dataclass
class DownloadProgress:
    """Progress information for downloads"""
    current: int
    total: int
    filename: str
    status: str
    error_message: Optional[str] = None


class GalleryDownloader:
    """Handles downloading gallery images"""

    def __init__(
        self, 
        api: NHentaiAPI,
        output_dir: str = "./downloads",
        delay: float = 0.5,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ):
        self.api = api
        self.output_dir = Path(output_dir)
        self.delay = delay
        self.progress_callback = progress_callback
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename for filesystem"""
        return _sanitize_filename(name, self.output_dir)

    def _find_folder(self, gallery: GalleryData) -> Path:
        """Find or create download folder"""
        base_name = self._sanitize_filename(gallery.english_title or str(gallery.id))
        folder = self.output_dir / base_name

        counter = 1
        original_folder = folder
        while folder.exists():
            id_file = folder / f".{gallery.id}"
            if id_file.exists():
                return folder

            folder = Path(f"{original_folder}.DUP{counter}")
            counter += 1

        folder.mkdir(parents=True, exist_ok=True)
        (folder / f".{gallery.id}").touch()

        return folder

    def _download_page(self, page: Page, dest_path: Path, retry: int = 3) -> bool:
        """Download single page with retry logic"""
        for attempt in range(retry):
            try:
                time.sleep(self.delay)

                response = self._session.get(
                    page.image_url,
                    timeout=30,
                    stream=True,
                    headers={'Referer': f"https://{self.api.host}/"},
                )
                response.raise_for_status()

                expected_length = response.headers.get('Content-Length')

                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                if expected_length:
                    actual_length = os.path.getsize(dest_path)
                    if int(expected_length) != actual_length:
                        os.remove(dest_path)
                        raise Exception(f"Size mismatch")

                try:
                    with Image.open(dest_path) as img:
                        img.verify()
                except Exception:
                    os.remove(dest_path)
                    raise Exception("Corrupted image file")

                return True

            except Exception as e:
                if attempt == retry - 1:
                    return False
                time.sleep(1)

        return False

    def download_archive(self, url: str, destination: Path) -> Path:
        """Download an API-issued gallery archive without reconstructing CDN URLs."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        for attempt, delay in enumerate((*RETRY_DELAYS, None), 1):
            try:
                response = request_with_retry(
                    self._session, 'GET', url, timeout=120, stream=True,
                )
                response.raise_for_status()
                with open(destination, 'wb') as archive:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            archive.write(chunk)
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError) as e:
                # Stream interrupted mid-download; start the archive over.
                destination.unlink(missing_ok=True)
                if delay is None:
                    raise
                print(f"Archive download interrupted ({type(e).__name__}), retrying in "
                      f"{delay}s (attempt {attempt + 1}/{len(RETRY_DELAYS) + 1})...")
                time.sleep(delay)
        if not zipfile.is_zipfile(destination):
            destination.unlink(missing_ok=True)
            raise Exception("The API download was not a valid ZIP archive")
        return destination

    @staticmethod
    def extract_archive(archive_path: Path, destination: Path) -> Path:
        """Safely extract an API archive for optional image/PDF output."""
        destination.mkdir(parents=True, exist_ok=True)
        root = destination.resolve()
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise Exception("Archive contains an unsafe file path")
            archive.extractall(destination)
        return destination

    def download_gallery(
        self, 
        gallery: GalleryData,
        start_page: int = 1,
        end_page: Optional[int] = None
    ) -> Optional[Path]:
        """Download gallery images"""
        folder = self._find_folder(gallery)

        pages = gallery.pages
        if end_page:
            pages = pages[start_page-1:end_page]
        else:
            pages = pages[start_page-1:]

        total = len(pages)

        failed_pages = []
        for i, page in enumerate(pages, 1):
            actual_page_num = start_page + i - 1
            filename = f"{actual_page_num:03d}.{page.extension}"
            dest_path = folder / filename

            if dest_path.exists():
                try:
                    with Image.open(dest_path) as img:
                        img.verify()
                    if self.progress_callback:
                        self.progress_callback(DownloadProgress(
                            current=i, total=total, filename=filename,
                            status="skipped"
                        ))
                    continue
                except:
                    pass

            if self.progress_callback:
                self.progress_callback(DownloadProgress(
                    current=i, total=total, filename=filename,
                    status="downloading"
                ))

            success = self._download_page(page, dest_path)

            if not success:
                failed_pages.append(actual_page_num)
                if self.progress_callback:
                    self.progress_callback(DownloadProgress(
                        current=i, total=total, filename=filename,
                        status="error", error_message="Failed to download"
                    ))

        if failed_pages:
            # Keep successfully downloaded pages so a later invocation can
            # resume, but do not report a partial gallery as successful.
            return None

        # Save metadata only after every requested page is present.
        metadata_path = folder / ".metadata.json"
        import json
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump({
                'id': gallery.id,
                'media_id': gallery.media_id,
                'title': gallery.title,
                'page_count': gallery.page_count,
                'language': gallery.language,
                'tags': [{'name': t.name, 'type': t.type.value} for t in gallery.tags]
            }, f, ensure_ascii=False, indent=2)

        return folder


class PDFConverter:
    """Converts downloaded galleries to PDF"""

    def __init__(
        self,
        output_dir: str = "./output",
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ):
        self.output_dir = Path(output_dir)
        self.progress_callback = progress_callback
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize filename for filesystem"""
        return _sanitize_filename(name, self.output_dir)

    def gallery_to_pdf(
        self, 
        gallery: GalleryData,
        image_folder: Path,
        output_filename: Optional[str] = None
    ) -> Optional[Path]:
        """Convert gallery images to PDF"""
        if not output_filename:
            output_filename = f"{self._sanitize_filename(gallery.english_title or str(gallery.id))}.pdf"

        output_path = self.output_dir / output_filename

        image_files = sorted([
            f for f in image_folder.rglob('*') if f.is_file()
            if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif']
        ], key=_natural_sort_key)

        if not image_files:
            return None

        c = canvas.Canvas(str(output_path))
        total = len(image_files)

        for i, img_path in enumerate(image_files, 1):
            if self.progress_callback:
                self.progress_callback(DownloadProgress(
                    current=i, total=total, filename=img_path.name,
                    status="converting"
                ))

            try:
                with Image.open(img_path) as img:
                    img_width, img_height = img.size

                aspect = img_height / img_width

                if aspect > 1.414:
                    page_width = 595
                    page_height = page_width * aspect
                else:
                    page_height = 842
                    page_width = page_height / aspect

                c.setPageSize((page_width, page_height))

                img_reader = ImageReader(str(img_path))
                c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)

                c.showPage()

            except Exception as e:
                if self.progress_callback:
                    self.progress_callback(DownloadProgress(
                        current=i, total=total, filename=img_path.name,
                        status="error", error_message=str(e)
                    ))

        c.save()

        if self.progress_callback:
            self.progress_callback(DownloadProgress(
                current=total, total=total, filename=output_filename,
                status="complete"
            ))

        return output_path

    def gallery_to_zip(
        self,
        gallery: GalleryData,
        image_folder: Path,
        output_filename: Optional[str] = None
    ) -> Optional[Path]:
        """Convert gallery images to ZIP archive"""
        if not output_filename:
            output_filename = f"{self._sanitize_filename(gallery.english_title or str(gallery.id))}.zip"

        output_path = self.output_dir / output_filename

        image_files = sorted([
            f for f in image_folder.rglob('*') if f.is_file()
            if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif']
        ], key=_natural_sort_key)

        if not image_files:
            return None

        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img_path in image_files:
                zf.write(img_path, img_path.name)

            import json
            metadata = {
                'id': gallery.id,
                'media_id': gallery.media_id,
                'title': gallery.title,
                'page_count': gallery.page_count,
                'language': gallery.language,
                'tags': [{'name': t.name, 'type': t.type.value} for t in gallery.tags]
            }
            zf.writestr('metadata.json', json.dumps(metadata, ensure_ascii=False, indent=2))

        return output_path


class DownloadManager:
    """High-level manager that combines download and conversion"""

    def __init__(
        self,
        download_dir: str = "./downloads",
        output_dir: str = "./output",
        delay: float = 0.5,
        host: str = "nhentai.net",
        cookie_file: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        self.api = NHentaiAPI(
            host=host, delay=delay, cookie_file=cookie_file,
            user_agent=user_agent,
        )
        self.downloader = GalleryDownloader(
            self.api, download_dir, delay, self._on_progress
        )
        self.converter = PDFConverter(output_dir, self._on_progress)
        self._current_progress: Optional[DownloadProgress] = None

    def _on_progress(self, progress: DownloadProgress):
        """Internal progress handler"""
        self._current_progress = progress
        print(f"[{progress.current}/{progress.total}] {progress.status}: {progress.filename}")

    def download_and_convert(
        self,
        gallery_id: int,
        to_pdf: bool = True,
        to_zip: bool = False,
        keep_images: bool = True
    ) -> dict:
        """Download gallery and convert to PDF/ZIP"""
        result = {
            'gallery': None,
            'download_folder': None,
            'pdf_path': None,
            'zip_path': None,
            'success': False
        }

        try:
            print(f"Fetching gallery {gallery_id}...")
            gallery = self.api.get_gallery(gallery_id)
            result['gallery'] = gallery

            print(f"Found: {gallery.english_title}")
            print(f"Pages: {gallery.page_count}")

            print("\nRequesting official gallery archive...")
            archive_url = self.api.get_download_url(gallery_id, "zip")
            archive_name = self.converter._sanitize_filename(
                gallery.english_title or str(gallery.id)
            ) + ".zip"
            archive_path = self.downloader.download_archive(
                archive_url, self.converter.output_dir / archive_name,
            )
            result['zip_path'] = archive_path if to_zip else None

            folder = None
            if to_pdf or keep_images:
                folder = self.downloader._find_folder(gallery)
                self.downloader.extract_archive(archive_path, folder)
                result['download_folder'] = folder

            if to_pdf:
                print("\nConverting to PDF...")
                pdf_path = self.converter.gallery_to_pdf(gallery, folder)
                result['pdf_path'] = pdf_path
                if pdf_path:
                    print(f"PDF saved: {pdf_path}")

            if to_zip:
                print(f"ZIP saved: {archive_path}")
            else:
                archive_path.unlink(missing_ok=True)

            if not keep_images and folder:
                import shutil
                shutil.rmtree(folder)
                print(f"\nCleaned up: {folder}")

            result['success'] = True

        except Exception as e:
            print(f"Error: {e}")
            result['error'] = str(e)

        return result
