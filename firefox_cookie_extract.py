#!/usr/bin/env python3
"""
Extract cookies from Firefox and test NHentai API
"""
import json
import sqlite3
import os
from pathlib import Path

def get_firefox_cookies(domain="nhentai.net"):
    """Extract cookies from Firefox's cookies.sqlite"""
    # Find Firefox profile
    firefox_path = Path.home() / "AppData/Roaming/Mozilla/Firefox/Profiles"
    
    if not firefox_path.exists():
        print("Firefox profile not found!")
        return {}
    
    # Find default profile
    profiles = list(firefox_path.glob("*.default*"))
    if not profiles:
        print("No Firefox profile found!")
        return {}
    
    profile = profiles[0]
    cookies_db = profile / "cookies.sqlite"
    
    if not cookies_db.exists():
        print("cookies.sqlite not found!")
        return {}
    
    # Copy to avoid lock issues
    import shutil
    temp_db = profile / "cookies_temp.sqlite"
    shutil.copy2(cookies_db, temp_db)
    
    try:
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, value, host, path 
            FROM moz_cookies 
            WHERE host LIKE ?
        """, (f"%{domain}%",))
        
        cookies = {}
        for name, value, host, path in cursor.fetchall():
            cookies[name] = value
            print(f"Found cookie: {name} (host: {host})")
        
        conn.close()
        return cookies
        
    finally:
        temp_db.unlink(missing_ok=True)

def main():
    print("Extracting Firefox cookies for nhentai.net...")
    cookies = get_firefox_cookies()
    
    if not cookies:
        print("No cookies found! Make sure you're logged into nhentai.net in Firefox")
        return
    
    # Save to JSON
    with open("cookies.json", "w") as f:
        json.dump(cookies, f, indent=2)
    
    print(f"\nSaved {len(cookies)} cookies to cookies.json")
    print("\nNow test with:")
    print("  python cookie_helper.py --cookies cookies.json")

if __name__ == "__main__":
    main()