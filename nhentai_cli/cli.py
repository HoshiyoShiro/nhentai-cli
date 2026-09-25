#!/usr/bin/env python3
"""
NHentai CLI - Command Line Interface for nhentai.net
Based on NClientV3 architecture
"""

import argparse
import sys
import json
from typing import List
from pathlib import Path

from .api_client import (
    NHentaiAPI, Tag, TagType, TagStatus, 
    SimpleGallery, GalleryData
)
from .downloader import DownloadManager


def format_gallery_list(galleries: List[SimpleGallery]) -> str:
    """Format gallery list for display"""
    lines = []
    for g in galleries:
        lang = f" [{g.language}]" if g.language else ""
        tags_str = ", ".join([t.name for t in g.tags[:5]])
        if len(g.tags) > 5:
            tags_str += f" +{len(g.tags)-5} more"
        elif not tags_str:
            tags_str = f"{len(g.tag_ids)} tag IDs (names require gallery info)"

        lines.append(f"┌─ {g.id}{lang}")
        lines.append(f"│ Title: {g.title[:80]}{'...' if len(g.title) > 80 else ''}")
        lines.append(f"│ Pages: {g.page_count} | Tags: {tags_str}")
        lines.append(f"└─ https://nhentai.net/g/{g.id}")
        lines.append("")

    return "\n".join(lines)


def format_gallery_detail(gallery: GalleryData) -> str:
    """Format detailed gallery info"""
    tags_by_type = {}
    for tag in gallery.tags:
        if tag.type.value not in tags_by_type:
            tags_by_type[tag.type.value] = []
        tags_by_type[tag.type.value].append(tag.name)

    lines = [
        "=" * 60,
        f"Gallery ID: {gallery.id}",
        f"Media ID: {gallery.media_id}",
        "",
        "TITLES:",
        f"  English: {gallery.english_title or 'N/A'}",
        f"  Japanese: {gallery.japanese_title or 'N/A'}",
        "",
        f"Pages: {gallery.page_count}",
        f"Language: {gallery.language or 'Unknown'}",
        f"Favorites: {gallery.favorite_count}",
        "",
        "TAGS:"
    ]

    for tag_type, names in sorted(tags_by_type.items()):
        lines.append(f"  {tag_type.upper()}: {', '.join(names)}")

    lines.extend([
        "",
        f"Cover: {gallery.cover.image_url if gallery.cover else 'N/A'}",
        f"URL: https://nhentai.net/g/{gallery.id}",
        "=" * 60
    ])

    return "\n".join(lines)


def get_api(args) -> NHentaiAPI:
    """Create an API instance using optional NHENTAI_API_KEY environment auth."""
    kwargs = {
        'host': args.host,
        'delay': args.delay,
        'user_agent': args.user_agent,
        'debug': getattr(args, 'debug', False)
    }

    return NHentaiAPI(**kwargs)


def cmd_search(args):
    """Handle search command"""
    api = get_api(args)

    tags = []
    if args.tag:
        for tag_name in args.tag:
            tags.append(Tag(
                id=0, 
                name=tag_name, 
                type=TagType.TAG,
                status=TagStatus.ACCEPTED
            ))

    if args.exclude_tag:
        for tag_name in args.exclude_tag:
            tags.append(Tag(
                id=0,
                name=tag_name,
                type=TagType.TAG,
                status=TagStatus.AVOIDED
            ))

    if not args.json:
        print(f"Searching: '{args.query}' with {len(tags)} tag filters...")
        print(f"Page: {args.page}, Sort: {args.sort}")
        print()

    try:
        results = api.search(
            query=args.query,
            tags=tags if tags else None,
            page=args.page,
            sort=args.sort
        )

        if not results:
            print("No results found.")
            return

        if not args.json:
            print(format_gallery_list(results))
            print(f"\nFound {len(results)} galleries")

        if args.json:
            output = []
            for g in results:
                output.append({
                    'id': g.id,
                    'title': g.title,
                    'media_id': g.media_id,
                    'page_count': g.page_count,
                    'language': g.language,
                    'tags': [{'name': t.name, 'type': t.type.value} for t in g.tags],
                    'tag_ids': g.tag_ids,
                    'url': f"https://nhentai.net/g/{g.id}"
                })
            print(json.dumps(output, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nTip: See https://nhentai.net/api/v2/docs for supported parameters and API-key setup.", file=sys.stderr)
        sys.exit(1)


def cmd_code(args):
    """Handle code search command"""
    api = get_api(args)

    print(f"Looking up gallery code: {args.code}")

    try:
        gallery = api.search_by_code(args.code)

        if not gallery:
            print(f"Gallery with code '{args.code}' not found.")
            sys.exit(1)

        if args.json:
            output = {
                'id': gallery.id,
                'media_id': gallery.media_id,
                'title': gallery.title,
                'page_count': gallery.page_count,
                'language': gallery.language,
                'tags': [{'name': t.name, 'type': t.type.value} for t in gallery.tags],
                'pages': [{'url': p.image_url, 'width': p.width, 'height': p.height} 
                         for p in gallery.pages[:5]],
                'url': f"https://nhentai.net/g/{gallery.id}"
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(format_gallery_detail(gallery))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nTip: See https://nhentai.net/api/v2/docs for supported parameters and API-key setup.", file=sys.stderr)
        sys.exit(1)


def cmd_info(args):
    """Handle info command"""
    api = get_api(args)

    print(f"Fetching metadata for gallery {args.id}...")

    try:
        gallery = api.get_gallery(args.id)

        if args.json:
            output = {
                'id': gallery.id,
                'media_id': gallery.media_id,
                'title': gallery.title,
                'page_count': gallery.page_count,
                'language': gallery.language,
                'favorite_count': gallery.favorite_count,
                'upload_date': gallery.upload_date,
                'tags': [{'name': t.name, 'type': t.type.value, 'count': t.count} 
                        for t in gallery.tags],
                'pages': [{'page': p.page_number, 'url': p.image_url, 
                          'width': p.width, 'height': p.height, 'ext': p.extension}
                         for p in gallery.pages],
                'cover': gallery.cover.image_url if gallery.cover else None,
                'thumbnail': gallery.thumbnail.image_url if gallery.thumbnail else None,
                'url': f"https://nhentai.net/g/{gallery.id}"
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(format_gallery_detail(gallery))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nTip: See https://nhentai.net/api/v2/docs for supported parameters and API-key setup.", file=sys.stderr)
        sys.exit(1)


def _load_gallery_ids(filename: str) -> List[int]:
    """Read one numeric gallery ID per line, preserving first-seen order."""
    source = Path(filename)
    if not source.is_file():
        raise ValueError(f"Code list file not found: {source}")

    ids = []
    seen = set()
    for line_number, raw_line in enumerate(source.read_text(encoding='utf-8').splitlines(), 1):
        value = raw_line.split('#', 1)[0].strip()
        if not value:
            continue
        if not value.isdecimal() or int(value) <= 0:
            raise ValueError(f"Invalid gallery code on line {line_number}: {raw_line!r}")
        gallery_id = int(value)
        if gallery_id not in seen:
            seen.add(gallery_id)
            ids.append(gallery_id)

    if not ids:
        raise ValueError("The code list contains no gallery IDs")
    return ids


def cmd_download(args):
    """Handle one gallery or a plain-text list of gallery IDs."""
    if args.id is not None and args.file:
        print("Error: provide either a gallery ID or --file, not both.", file=sys.stderr)
        sys.exit(2)
    if args.id is None and not args.file:
        print("Error: provide a gallery ID or --file CODES.txt.", file=sys.stderr)
        sys.exit(2)
    try:
        gallery_ids = _load_gallery_ids(args.file) if args.file else [args.id]
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)

    manager = DownloadManager(
        download_dir=args.output,
        output_dir=args.output,
        delay=args.delay,
        host=args.host,
    )

    print(f"Output directory: {args.output}")
    print(f"Galleries queued: {len(gallery_ids)}")
    failures = []

    for index, gallery_id in enumerate(gallery_ids, 1):
        print(f"\n[{index}/{len(gallery_ids)}] Downloading gallery {gallery_id}...")
        result = manager.download_and_convert(
            gallery_id=gallery_id,
            to_pdf=args.pdf,
            to_zip=args.zip,
            keep_images=not args.cleanup
        )

        if result['success']:
            if result['pdf_path']:
                print(f"PDF: {result['pdf_path']}")
            if result['zip_path']:
                print(f"ZIP: {result['zip_path']}")
            if result['download_folder'] and not args.cleanup:
                print(f"Images: {result['download_folder']}")
        else:
            failures.append(gallery_id)
            print(f"Download failed for {gallery_id}: {result.get('error', 'unknown error')}", file=sys.stderr)

    if failures:
        print(f"\nCompleted with {len(failures)} failed gallery(s): {', '.join(map(str, failures))}", file=sys.stderr)
        sys.exit(1)

    print(f"\nDOWNLOAD COMPLETE: {len(gallery_ids)} gallery(s)")


def cmd_random(args):
    """Handle random command"""
    api = get_api(args)

    print("Fetching random gallery...")

    try:
        gallery = api.get_random()

        if args.json:
            output = {
                'id': gallery.id,
                'media_id': gallery.media_id,
                'title': gallery.title,
                'page_count': gallery.page_count,
                'language': gallery.language,
                'tags': [{'name': t.name, 'type': t.type.value} for t in gallery.tags],
                'url': f"https://nhentai.net/g/{gallery.id}"
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(format_gallery_detail(gallery))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Gallery titles often contain Japanese/accented text; avoid crashes on
    # consoles or redirected output that default to a legacy code page.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(
        description="NHentai CLI - Browse and download galleries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s search "naruto"
  %(prog)s search --tag "sole female" --tag "big breasts"
  %(prog)s search --exclude-tag "yaoi" --exclude-tag "furry"
  %(prog)s code 682928
  %(prog)s info 682928 --json
  %(prog)s download 682928 --pdf --output ./downloads
  %(prog)s download --file codes.txt --zip
  %(prog)s random

API key (optional for browsing; required for official downloads):
  Set NHENTAI_API_KEY locally, then run %(prog)s normally.
        """
    )

    parser.add_argument(
        '--host', 
        default='nhentai.net',
        help='Mirror host (default: nhentai.net)'
    )
    parser.add_argument(
        '--delay', 
        type=float, 
        default=0.5,
        help='Request delay in seconds (default: 0.5)'
    )
    parser.add_argument(
        '--user-agent',
        help='Custom User-Agent header for API requests'
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug output'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search galleries')
    search_parser.add_argument('query', nargs='?', default='', help='Search query')
    search_parser.add_argument('--tag', '-t', action='append', help='Include tag (can use multiple)')
    search_parser.add_argument('--exclude-tag', '-e', action='append', help='Exclude tag (can use multiple)')
    search_parser.add_argument('--page', '-p', type=int, default=1, help='Page number')
    search_parser.add_argument('--sort', '-s', default='date', 
                             choices=['date', 'popular-today', 'popular-week', 'popular-month', 'popular'],
                             help='Sort order')
    search_parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    search_parser.set_defaults(func=cmd_search)

    # Code command
    code_parser = subparsers.add_parser('code', help='Search by gallery code')
    code_parser.add_argument('code', help='6-digit gallery code')
    code_parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    code_parser.set_defaults(func=cmd_code)

    # Info command
    info_parser = subparsers.add_parser('info', help='Get gallery metadata')
    info_parser.add_argument('id', type=int, help='Gallery ID')
    info_parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    info_parser.set_defaults(func=cmd_info)

    # Download command
    download_parser = subparsers.add_parser('download', help='Download gallery')
    download_parser.add_argument('id', type=int, nargs='?', help='Single gallery ID')
    download_parser.add_argument('--file', '-f', help='Text file with one gallery ID per line')
    download_parser.add_argument('--pdf', action='store_true', default=True, help='Convert to PDF (default)')
    download_parser.add_argument('--no-pdf', dest='pdf', action='store_false', help='Skip PDF conversion')
    download_parser.add_argument('--zip', '-z', action='store_true', help='Create ZIP archive')
    download_parser.add_argument('--output', '-o', default='./downloads', help='Output directory')
    download_parser.add_argument('--cleanup', action='store_true', help='Delete images after conversion')
    download_parser.set_defaults(func=cmd_download)

    # Random command
    random_parser = subparsers.add_parser('random', help='Get random gallery')
    random_parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')
    random_parser.set_defaults(func=cmd_random)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
