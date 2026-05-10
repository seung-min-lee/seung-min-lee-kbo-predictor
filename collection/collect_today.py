"""오늘 배당만 수집 (Next Matches)"""
import os as _os, sys as _sys
_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_os.chdir(_root); _sys.path.insert(0, _root)
from playwright.sync_api import sync_playwright
from kbo_playwright_scrape import get_next_matches, update_games_csv
import time

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    next_matches = get_next_matches(page)
    browser.close()

update_games_csv(next_matches)

import json
if next_matches:
    for m in next_matches:
        print(f"  {m['date']} slot{int(m['slot'])}: {m['home']} vs {m['away']} | home={m['home_odds']} away={m['away_odds']}")
