#!/usr/bin/env python3
"""
Cookie Helper for NHentai CLI

This script helps you extract cookies from your browser and use them
with the NHentai CLI to bypass Cloudflare protection.

Usage:
    1. Open nhentai.net in your browser and complete any Cloudflare challenge
    2. Export cookies using one of the methods below
    3. Run: python cookie_helper.py --cookies cookies.json
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Optional

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))

from nhentai_cli.api_client import NHentaiAPI


def extract_from_netscape(input_file: str, output_file: str):
    """Convert Netscape format cookies (from browser extensions) to JSON"""
    cookies = {}

    with open(input_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split('\t')
            if len(parts) >= 7:
                domain = parts[0]
                name = parts[5]
                value = parts[6]

                if 'nhentai' in domain:
                    cookies[name] = value

    with open(output_file, 'w') as f:
        json.dump(cookies, f, indent=2)

    print(f"Extracted {len(cookies)} cookies for nhentai.net")
    print(f"Saved to: {output_file}")
    return cookies


def test_api_with_cookies(cookie_file: str, user_agent: Optional[str] = None):
    """Test API connection with cookies"""
    print("Testing NHentai API with cookies...")
    print("=" * 50)

    try:
        api = NHentaiAPI(
            cookie_file=cookie_file, delay=1.0, user_agent=user_agent,
        )

        # Test 1: Get gallery info
        print("\n1. Testing gallery fetch (ID: 574323)...")
        gallery = api.get_gallery(574323)
        print(f"   SUCCESS: {gallery.english_title[:50]}...")
        print(f"   Pages: {gallery.page_count}")

        # Test 2: Search
        print("\n2. Testing search...")
        results = api.search(query="naruto", page=1)
        print(f"   Found {len(results)} results")

        print("\n" + "=" * 50)
        print("All tests passed! Cookies are working.")

        # Save working cookies
        api.save_cookies("working_cookies.json")

    except Exception as e:
        print(f"\nFAILED: {e}")
        print("\nPossible issues:")
        print("- Cookies expired (get fresh ones from browser)")
        print("- Wrong cookie format")
        print("- IP address changed since getting cookies")
        sys.exit(1)


def show_manual_instructions():
    """Show instructions for manual cookie extraction"""
    print("""
=== HOW TO GET COOKIES FROM YOUR BROWSER ===

METHOD 1: Using Browser Extension (Recommended)
1. Install "Get cookies.txt LOCALLY" extension (Chrome/Firefox)
2. Go to nhentai.net and complete any Cloudflare challenge
3. Click the extension icon → Export cookies
4. Save as "cookies.txt"
5. Run: python cookie_helper.py --convert cookies.txt --output cookies.json

METHOD 2: Using Developer Tools
1. Go to nhentai.net in your browser
2. Press F12 → Application/Storage tab → Cookies
3. Find cookies for "nhentai.net"
4. Copy values for: cf_clearance, csrftoken, sessionid
5. Create cookies.json:
   {
     "cf_clearance": "your_value_here",
     "csrftoken": "your_value_here"
   }

METHOD 3: Using JavaScript Console
1. Go to nhentai.net
2. Press F12 → Console tab
3. Paste this code:
   copy(JSON.stringify(Object.fromEntries(document.cookie.split('; ').map(c => c.split('=')))))
4. Paste the copied text into cookies.json

=== IMPORTANT NOTES ===
- Cookies are tied to your IP address - don't use VPN after extracting
- cf_clearance expires after ~30 minutes to a few hours
- You may need to re-extract cookies periodically
""")


def main():
    parser = argparse.ArgumentParser(
        description="Cookie helper for NHentai CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--cookies', '-c', help='Path to cookies JSON file')
    parser.add_argument(
        '--user-agent',
        help='Browser User-Agent associated with the exported cookies'
    )
    parser.add_argument('--convert', help='Convert Netscape cookies.txt to JSON')
    parser.add_argument('--output', '-o', default='cookies.json', help='Output file for converted cookies')
    parser.add_argument('--instructions', '-i', action='store_true', help='Show manual extraction instructions')

    args = parser.parse_args()

    if args.instructions:
        show_manual_instructions()
        return

    if args.convert:
        extract_from_netscape(args.convert, args.output)
        return

    if args.cookies:
        test_api_with_cookies(args.cookies, args.user_agent)
        return

    # Default: show instructions
    show_manual_instructions()


if __name__ == "__main__":
    main()
