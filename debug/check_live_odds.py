"""오늘 현재 배당 수집 후 open과 비교해 방향 출력"""
from playwright.sync_api import sync_playwright
from kbo_playwright_scrape import GAMES_URL, JS_NEXT_MATCHES, TEAM_MAP, normalize_date
import json, time
from datetime import datetime as _dt

TODAY = _dt.today().strftime('%Y-%m-%d')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    page.goto(GAMES_URL, timeout=90000, wait_until='domcontentloaded')
    page.wait_for_selector('div.eventRow', timeout=45000)
    time.sleep(3)
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)
    raw = page.evaluate(JS_NEXT_MATCHES)
    browser.close()

# open 배당 불러오기
with open('kbo_today_odds.json', encoding='utf-8') as f:
    open_odds = json.load(f)

# open 배당을 (home, away) 기준으로 재색인
open_by_team = {}
for key, val in open_odds.items():
    open_by_team[(val['home'], val['away'])] = val

# 현재 배당 정리 (중복 제거)
seen = set()
current = []
for m in raw:
    norm = normalize_date(m['date'])
    if norm != TODAY:
        continue
    home = TEAM_MAP.get(m['home'], m['home'])
    away = TEAM_MAP.get(m['away'], m['away'])
    if (home, away) in seen:
        continue
    seen.add((home, away))
    current.append({'home': home, 'away': away,
                    'home_now': m.get('home_odds'), 'away_now': m.get('away_odds')})

# open_odds 슬롯 순서로 정렬
slot_order = {(v['home'], v['away']): v['slot'] for v in open_odds.values()}
current.sort(key=lambda x: slot_order.get((x['home'], x['away']), 99))

print(f"{'Slot':<5} {'홈팀':<20} {'원정팀':<20} {'홈open':>7} {'홈now':>7} {'홈방향':>5} {'원정open':>9} {'원정now':>8} {'원정방향':>6}")
print('-' * 90)
for cur in current:
    op = open_by_team.get((cur['home'], cur['away']), {})
    slot = slot_order.get((cur['home'], cur['away']), '?')
    h_open = op.get('home_odds')
    a_open = op.get('away_odds')
    h_now  = cur['home_now']
    a_now  = cur['away_now']
    h_dir = ('↑' if h_now > h_open else '↓' if h_now < h_open else '→') if h_open and h_now else '?'
    a_dir = ('↑' if a_now > a_open else '↓' if a_now < a_open else '→') if a_open and a_now else '?'
    print(f"{int(slot):<5} {cur['home']:<20} {cur['away']:<20} {str(h_open):>7} {str(h_now):>7} {h_dir:>5} {str(a_open):>9} {str(a_now):>8} {a_dir:>6}")
