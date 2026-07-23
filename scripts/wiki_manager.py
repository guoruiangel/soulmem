#!/usr/bin/env python3
# ============================================================================
# SoulMem — Wiki Manager Module
# Encapsulates all wiki operations: login, CRUD, service management.
#
# Usage:
#   from wiki_manager import WikiManager
#   wm = WikiManager()
#   wm.login()
#   wm.create_page("title", "slug", "# content")
#   wm.update_page("slug", "# new content")
# ============================================================================

import os
import sys
import json
import sqlite3
import subprocess
import time
import requests
from pathlib import Path
from datetime import datetime

# Configuration
WIKI_HOST = "http://192.168.1.83:5003"
WIKI_DIR = Path(os.path.expanduser("~/.openclaw/workspace/wiki"))
DB_PATH = WIKI_DIR / "wiki.db"
APP_PATH = WIKI_DIR / "wiki_app.py"
COOKIE_FILE = "/tmp/wiki_session.txt"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin123"


class WikiManager:
    """Wiki operations manager"""
    
    def __init__(self, host=WIKI_HOST):
        self.host = host
        self.session = requests.Session()
        self._load_cookie()
    
    def _load_cookie(self):
        """Load cookie from file"""
        if os.path.exists(COOKIE_FILE):
            with open(COOKIE_FILE) as f:
                cookie = f.read().strip()
                if cookie:
                    # Parse Netscape cookie format
                    for line in cookie.split('\n'):
                        if line.startswith('#') or not line.strip():
                            continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            self.session.cookies.set(parts[5], parts[6])
    
    def _save_cookie(self, response):
        """Save cookie from response"""
        with open(COOKIE_FILE, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in self.session.cookies:
                f.write(f".\tTRUE\t/\tTRUE\t{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n")
    
    # ========================================
    # Auth
    # ========================================
    
    def login(self, username=DEFAULT_USER, password=DEFAULT_PASS):
        """Login and save cookie"""
        resp = self.session.post(
            f"{self.host}/wiki/login",
            data={"username": username, "password": password},
            allow_redirects=True
        )
        
        if resp.status_code == 200 and "logout" in resp.text.lower():
            self._save_cookie(resp)
            return True
        return False
    
    def is_logged_in(self):
        """Check if session is valid"""
        try:
            resp = self.session.get(f"{self.host}/wiki/", timeout=5)
            return "logout" in resp.text.lower() or "新建页面" in resp.text
        except:
            return False
    
    def ensure_logged_in(self):
        """Auto-login if needed"""
        if not self.is_logged_in():
            return self.login()
        return True
    
    # ========================================
    # Page CRUD
    # ========================================
    
    def list_pages(self):
        """List all pages"""
        if not self.ensure_logged_in():
            return None
        
        resp = self.session.get(f"{self.host}/wiki/api/pages")
        if resp.status_code == 200:
            return resp.json()
        return None
    
    def get_page(self, slug):
        """Get single page content"""
        if not self.ensure_logged_in():
            return None
        
        resp = self.session.get(f"{self.host}/wiki/api/pages/{slug}")
        if resp.status_code == 200:
            return resp.json()
        return None
    
    def create_page(self, title, slug=None, content="", parent_id=None):
        """Create a new page"""
        if not self.ensure_logged_in():
            return None
        
        if not slug:
            slug = self._slugify(title)
        
        data = {
            "title": title,
            "slug": slug,
            "content": content,
            "parent_id": parent_id,
        }
        
        resp = self.session.post(
            f"{self.host}/wiki/api/pages",
            json=data,
            headers={"Content-Type": "application/json"}
        )
        
        if resp.status_code == 200:
            return resp.json()
        return None
    
    def update_page(self, slug, content=None, title=None):
        """Update page content"""
        if not self.ensure_logged_in():
            return None
        
        # Get current page first
        current = self.get_page(slug)
        if not current:
            return None
        
        data = {
            "title": title or current.get("title", ""),
            "content": content if content is not None else current.get("content", ""),
        }
        
        resp = self.session.put(
            f"{self.host}/wiki/api/pages/{slug}",
            json=data,
            headers={"Content-Type": "application/json"}
        )
        
        if resp.status_code == 200:
            return resp.json()
        return None
    
    def delete_page(self, slug):
        """Delete (unpublish) a page"""
        if not self.ensure_logged_in():
            return None
        
        resp = self.session.delete(f"{self.host}/wiki/api/pages/{slug}")
        if resp.status_code == 200:
            return resp.json()
        return None
    
    def get_history(self, slug):
        """Get page history"""
        if not self.ensure_logged_in():
            return None
        
        resp = self.session.get(f"{self.host}/wiki/api/pages/{slug}/history")
        if resp.status_code == 200:
            return resp.json()
        return None
    
    def rollback(self, slug, version):
        """Rollback to a specific version"""
        if not self.ensure_logged_in():
            return None
        
        resp = self.session.post(f"{self.host}/wiki/api/pages/{slug}/rollback/{version}")
        if resp.status_code == 200:
            return resp.json()
        return None
    
    # ========================================
    # Direct DB operations (fallback)
    # ========================================
    
    def db_update_page(self, slug, content):
        """Update page directly in database"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("UPDATE pages SET content = ?, updated_at = ? WHERE slug = ?",
                        (content, datetime.now().isoformat(), slug))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"DB error: {e}")
            return False
    
    def db_insert_page(self, title, slug, content, created_by=1):
        """Insert page directly in database"""
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""
                INSERT OR IGNORE INTO pages (title, slug, content, content_html, created_by)
                VALUES (?, ?, ?, ?, ?)
            """, (title, slug, content, "", created_by))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"DB error: {e}")
            return False
    
    # ========================================
    # Service management
    # ========================================
    
    def is_running(self):
        """Check if wiki service is running"""
        try:
            resp = self.session.get(f"{self.host}/wiki/", timeout=3)
            return resp.status_code == 200
        except:
            return False
    
    def start_service(self):
        """Start wiki service"""
        if self.is_running():
            return True
        
        subprocess.Popen(
            [sys.executable, str(APP_PATH)],
            cwd=str(WIKI_DIR),
            stdout=open("/tmp/wiki_server.log", "w"),
            stderr=subprocess.STDOUT
        )
        
        # Wait for startup
        for _ in range(10):
            time.sleep(1)
            if self.is_running():
                return True
        return False
    
    def stop_service(self):
        """Stop wiki service"""
        os.system("kill $(lsof -ti :5003) 2>/dev/null")
        time.sleep(1)
        return not self.is_running()
    
    def restart_service(self):
        """Restart wiki service"""
        self.stop_service()
        time.sleep(2)
        return self.start_service()
    
    # ========================================
    # Utility
    # ========================================
    
    def _slugify(self, text):
        """Simple slug generator"""
        import re
        text = text.lower().strip()
        text = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-') or f"page-{int(time.time())}"
    
    def health_check(self):
        """Full health check"""
        result = {
            "service_running": self.is_running(),
            "logged_in": self.is_logged_in(),
            "db_exists": DB_PATH.exists(),
            "app_exists": APP_PATH.exists(),
        }
        
        if result["service_running"]:
            pages = self.list_pages()
            result["page_count"] = len(pages) if pages else 0
        
        return result


# ========================================
# CLI interface
# ========================================

def main():
    import argparse
    
    p = argparse.ArgumentParser(description="SoulMem Wiki Manager")
    sub = p.add_subparsers(dest="command")
    
    # Status
    sub.add_parser("status", help="Check wiki status")
    
    # Login
    login_p = sub.add_parser("login", help="Login to wiki")
    login_p.add_argument("--user", default=DEFAULT_USER)
    login_p.add_argument("--password", default=DEFAULT_PASS)
    
    # List
    sub.add_parser("list", help="List all pages")
    
    # Get
    get_p = sub.add_parser("get", help="Get page content")
    get_p.add_argument("slug", help="Page slug")
    
    # Create
    create_p = sub.add_parser("create", help="Create a page")
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--slug", default=None)
    create_p.add_argument("--content", default="")
    create_p.add_argument("--parent", type=int, default=None)
    
    # Update
    update_p = sub.add_parser("update", help="Update a page")
    update_p.add_argument("slug", help="Page slug")
    update_p.add_argument("--content", required=True)
    
    # Delete
    del_p = sub.add_parser("delete", help="Delete a page")
    del_p.add_argument("slug", help="Page slug")
    
    # History
    hist_p = sub.add_parser("history", help="Get page history")
    hist_p.add_argument("slug", help="Page slug")
    
    # Service
    sub.add_parser("start", help="Start wiki service")
    sub.add_parser("stop", help="Stop wiki service")
    sub.add_parser("restart", help="Restart wiki service")
    
    args = p.parse_args()
    
    if not args.command:
        p.print_help()
        return
    
    wm = WikiManager()
    
    if args.command == "status":
        result = wm.health_check()
        print(json.dumps(result, indent=2))
    
    elif args.command == "login":
        if wm.login(args.user, args.password):
            print("✅ Login successful")
        else:
            print("❌ Login failed")
    
    elif args.command == "list":
        pages = wm.list_pages()
        if pages:
            for p in pages:
                print(f"  {p['id']:3} | {p['slug']:30} | {p['title']}")
        else:
            print("No pages or not logged in")
    
    elif args.command == "get":
        page = wm.get_page(args.slug)
        if page:
            print(f"Title: {page.get('title')}")
            print(f"Content:\n{page.get('content', '')[:500]}")
        else:
            print("Page not found")
    
    elif args.command == "create":
        result = wm.create_page(args.title, args.slug, args.content, args.parent)
        if result:
            print(f"✅ Created: {result.get('slug')}")
        else:
            print("❌ Create failed")
    
    elif args.command == "update":
        result = wm.update_page(args.slug, args.content)
        if result:
            print(f"✅ Updated: {args.slug}")
        else:
            print("❌ Update failed")
    
    elif args.command == "delete":
        result = wm.delete_page(args.slug)
        if result:
            print(f"✅ Deleted: {args.slug}")
        else:
            print("❌ Delete failed")
    
    elif args.command == "history":
        history = wm.history(args.slug)
        if history:
            for h in history:
                print(f"  v{h['version']} | {h['edited_at']} | {h.get('summary', '')}")
        else:
            print("No history")
    
    elif args.command == "start":
        if wm.start_service():
            print("✅ Service started")
        else:
            print("❌ Failed to start")
    
    elif args.command == "stop":
        if wm.stop_service():
            print("✅ Service stopped")
        else:
            print("❌ Failed to stop")
    
    elif args.command == "restart":
        if wm.restart_service():
            print("✅ Service restarted")
        else:
            print("❌ Failed to restart")


if __name__ == "__main__":
    main()
