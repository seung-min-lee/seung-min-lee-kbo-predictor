from playwright.sync_api import sync_playwright
import sys
sys.path.insert(0, '.')
from kbo_playwright_scrape import get_next_matches

print('Next Matches 수집 시작...')
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    matches = get_next_matches(page)
    browser.close()

print(f'수집된 경기: {len(matches)}개')
for m in matches:
    print(f"  {m['date']} slot{int(m['slot'])}: {m['home']} vs {m['away']} | home={m['home_odds']} away={m['away_odds']}")
