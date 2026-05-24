"""
05-23, 05-24 BM 재수집 (전체 URL 포함)
- Playwright로 전체 URL 수집
- Selenium으로 BM open/close 수집 (전체 URL 사용)
- kbo_games.csv 슬롯 기준으로 저장
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, re, time
import numpy as np
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime as _dt, timedelta as _td

RESULTS_URL = 'https://www.oddsportal.com/baseball/south-korea/kbo/results/'
FAKE_BMS    = {'My coupon', 'User Predictions', 'Betfair Exchange'}

TEAM_MAP = {
    'Doosan Bears': 'Doosan Bears', 'NC Dinos': 'NC Dinos',
    'Hanwha Eagles': 'Hanwha Eagles', 'Lotte Giants': 'Lotte Giants',
    'KIA Tigers': 'KIA Tigers', 'LG Twins': 'LG Twins',
    'Kiwoom Heroes': 'Kiwoom Heroes', 'SSG Landers': 'SSG Landers',
    'KT Wiz Suwon': 'KT Wiz Suwon', 'Samsung Lions': 'Samsung Lions',
}

def normalize_date(raw):
    s = str(raw).strip()
    today = _dt.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        return (today - _td(days=1)).strftime('%Y-%m-%d')
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return _dt.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s

JS_EXTRACT = """
() => {
    const results=[], seen=new Set();
    let currentDate='';
    document.querySelectorAll('div.eventRow').forEach(row=>{
        const dateEl=row.querySelector('[data-testid="date-header"]');
        if(dateEl&&dateEl.innerText.trim()) currentDate=dateEl.innerText.trim();
        const link=row.querySelector('a[href*="/h2h/"]');
        if(!link) return;
        const href=link.href;
        if(!href.includes('#')||seen.has(href)) return;
        seen.add(href);
        const teams=[...row.querySelectorAll('p.participant-name')]
            .map(el=>el.innerText.trim()).filter(Boolean).slice(0,2);
        const nums=[...row.querySelectorAll('[data-v-115522af]')]
            .map(el=>el.innerText.trim()).filter(t=>/^\\d+$/.test(t));
        const homeScore=parseInt(nums[0]);
        const awayScore=parseInt(nums[2]);
        results.push({
            date:currentDate, url:href,
            match_id:href.split('#')[1],
            home:teams[0]||'', away:teams[1]||'',
            home_score:isNaN(homeScore)?null:homeScore,
            away_score:isNaN(awayScore)?null:awayScore,
            winner_is_home:(!isNaN(homeScore)&&!isNaN(awayScore))?homeScore>awayScore:null,
            finished:!isNaN(homeScore)&&!isNaN(awayScore)
        });
    });
    return results;
}
"""

def fetch_match_urls(target_dates):
    """Playwright로 결과 페이지에서 전체 URL 수집"""
    found = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080}
        )
        page = ctx.new_page()
        try:
            page.goto(RESULTS_URL, timeout=90000, wait_until='domcontentloaded')
            page.wait_for_selector('div.eventRow', timeout=30000)
        except PWTimeout:
            print('결과 페이지 로딩 실패')
            browser.close()
            return found

        time.sleep(3)
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(2)
        raw = page.evaluate(JS_EXTRACT)
        print(f'수집된 경기: {len(raw)}개')

        for m in raw:
            d = normalize_date(m['date'])
            if d not in target_dates:
                continue
            home = TEAM_MAP.get(m['home'], m['home'])
            away = TEAM_MAP.get(m['away'], m['away'])
            found.setdefault(d, []).append({
                'date': d, 'home': home, 'away': away,
                'url': m['url'],
                'match_id': m['match_id'],
                'winner_is_home': m['winner_is_home'],
                'home_score': m['home_score'],
                'away_score': m['away_score'],
            })
            print(f'  {d}: {home} vs {away}  url={m["url"]}')

        browser.close()
    return found


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-gpu')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


def accept_cookies(driver):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
        if btn.is_displayed():
            driver.execute_script('arguments[0].click();', btn)
            time.sleep(1.5)
    except:
        pass


def parse_val(s):
    m = re.findall(r'\d+\.\d+', str(s))
    return float(m[0]) if m else None


def get_open_from_tooltip(driver, cell_idx):
    try:
        cells = driver.find_elements(By.CSS_SELECTOR, 'div.odds-cell')
        if cell_idx >= len(cells):
            return None
        cell = cells[cell_idx]
        driver.execute_script('arguments[0].scrollIntoView(true);', cell)
        driver.execute_script('window.scrollBy(0,-200);')
        time.sleep(0.3)
        ActionChains(driver).move_to_element(cell).click().perform()
        time.sleep(1.8)
        tips = driver.find_elements(By.CSS_SELECTOR, '[class*="odds-tooltip"]')
        for tip in tips:
            txt = tip.text.strip()
            if 'Opening' not in txt:
                continue
            lines = [l.strip() for l in txt.split('\n') if l.strip()]
            for i, line in enumerate(lines):
                if 'Opening odds' in line and i + 2 < len(lines):
                    m2 = re.findall(r'\d+\.\d+', lines[i + 2])
                    if m2:
                        return float(m2[0])
    except:
        pass
    return None


def scrape_bm_odds(driver, url, first=False):
    """전체 URL(hash 포함) 사용"""
    driver.get(url)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(3)
    except:
        time.sleep(5)
    if first:
        accept_cookies(driver)
        time.sleep(1)

    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    bm_names = [n.text.strip() for n in name_els
                if n.text.strip() and n.text.strip() not in FAKE_BMS]
    if not bm_names:
        return {}

    odds_els = driver.find_elements(By.CSS_SELECTOR, 'p.odds-text')
    close_vals = [parse_val(e.text.strip()) for e in odds_els]
    close_vals = [v for v in close_vals if v is not None]
    print(f'  BM {len(bm_names)}개 | close {len(close_vals)}개')

    if len(close_vals) < len(bm_names) * 2:
        print('  close 값 부족 - 재시도')
        time.sleep(3)
        odds_els = driver.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        close_vals = [parse_val(e.text.strip()) for e in odds_els]
        close_vals = [v for v in close_vals if v is not None]

    result = {}
    for i, bm in enumerate(bm_names):
        h_c = close_vals[i*2]   if i*2   < len(close_vals) else None
        a_c = close_vals[i*2+1] if i*2+1 < len(close_vals) else None
        h_o = get_open_from_tooltip(driver, i*2)
        a_o = get_open_from_tooltip(driver, i*2+1)
        result[bm] = {'home_open': h_o, 'home_close': h_c, 'away_open': a_o, 'away_close': a_c}
    return result


def calc_wd(ho, hc, ao, ac, wih):
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [ho, hc, ao, ac]):
            return np.nan
        hchg = float(hc) - float(ho)
        achg = float(ac) - float(ao)
        wchg = hchg if wih else achg
        lchg = achg if wih else hchg
        if abs(wchg - lchg) < 0.001:
            return np.nan
        return 1.0 if wchg > lchg else 0.0
    except:
        return np.nan


def update_odds_csv(df, date, slot, home, away, wih, bm_data, match_id=None):
    mask_game = (df['date'] == date) & (df['slot'] == slot)
    updated = 0
    for bm, vals in bm_data.items():
        mask_bm = mask_game & (df['bookmaker'] == bm)
        h_o = vals.get('home_open')
        h_c = vals.get('home_close')
        a_o = vals.get('away_open')
        a_c = vals.get('away_close')
        if not any(mask_bm):
            if h_c is None or a_c is None:
                continue
            mid = match_id or ''
            new_row = {
                'match_id': mid, 'date': date, 'slot': slot,
                'home': home, 'away': away,
                'winner': None, 'winner_is_home': wih,
                'bookmaker': bm,
                'home_open': h_o, 'home_close': h_c,
                'home_change': round(h_c - h_o, 4) if h_o else None,
                'home_direction': (1 if h_c < h_o else (-1 if h_c > h_o else 0)) if h_o else None,
                'away_open': a_o, 'away_close': a_c,
                'away_change': round(a_c - a_o, 4) if a_o else None,
                'away_direction': None,
                'winner_direction': calc_wd(h_o, h_c, a_o, a_c, wih),
                'odds_ratio': round(h_c / a_c, 4) if a_c else None,
                'consensus': 'home' if h_c < a_c else 'away',
                'consensus_win': None,
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            updated += 1
        else:
            existing = df[mask_bm].iloc[0]
            if h_o is None: h_o = existing['home_open'] if pd.notna(existing.get('home_open')) else None
            if a_o is None: a_o = existing['away_open'] if pd.notna(existing.get('away_open')) else None
            if h_c is None: h_c = existing['home_close'] if pd.notna(existing.get('home_close')) else None
            if a_c is None: a_c = existing['away_close'] if pd.notna(existing.get('away_close')) else None
            if h_o is not None: df.loc[mask_bm, 'home_open']  = h_o
            if h_c is not None: df.loc[mask_bm, 'home_close'] = h_c
            if a_o is not None: df.loc[mask_bm, 'away_open']  = a_o
            if a_c is not None: df.loc[mask_bm, 'away_close'] = a_c
            if h_o and h_c:
                df.loc[mask_bm, 'home_change']    = round(h_c - h_o, 4)
                df.loc[mask_bm, 'home_direction'] = 1 if h_c < h_o else (-1 if h_c > h_o else 0)
            wd_wih = bool(existing.get('winner_is_home', wih)) if wih is None else wih
            wd = calc_wd(h_o, h_c, a_o, a_c, wd_wih)
            if not (isinstance(wd, float) and np.isnan(wd)):
                df.loc[mask_bm, 'winner_direction'] = wd
            updated += 1
    return df, updated


# ── 메인 ─────────────────────────────────────────────────────────
TARGET_DATES = ['2026-05-23', '2026-05-24']

print('======= STEP 1: 전체 URL 수집 =======')
matches_by_date = fetch_match_urls(TARGET_DATES)

# kbo_games.csv에서 슬롯 정보 로드 (home/away → slot 매핑)
g = pd.read_csv('kbo_games.csv')
slot_map = {}  # (date, home, away) -> slot
for _, r in g.iterrows():
    slot_map[(r['date'], r['home'], r['away'])] = r['slot']

print('\n======= STEP 2: Selenium BM 수집 =======')
df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
first_load = True

try:
    for date in TARGET_DATES:
        if date not in matches_by_date:
            print(f'\n{date}: 수집된 경기 없음')
            continue
        print(f'\n========== {date} BM 수집 ==========')
        for m in matches_by_date[date]:
            home = m['home']; away = m['away']
            url  = m['url']
            wih  = m.get('winner_is_home')
            mid  = m.get('match_id', '')

            # kbo_games.csv에서 올바른 slot 조회
            slot = slot_map.get((date, home, away))
            if slot is None:
                print(f'  {home} vs {away}: kbo_games.csv에 없음 - 스킵')
                continue

            print(f'\n[{date} slot{int(slot)}] {home} vs {away}  wih={wih}')
            print(f'  URL: {url}')
            bm_data = scrape_bm_odds(driver, url, first=first_load)
            first_load = False

            if not bm_data:
                print('  수집 실패')
                continue

            for bm, v in list(bm_data.items())[:3]:
                print(f'  {bm}: h_o={v["home_open"]} h_c={v["home_close"]}  a_o={v["away_open"]} a_c={v["away_close"]}')

            df, n = update_odds_csv(df, date, slot, home, away, wih, bm_data, match_id=mid)
            df.to_csv('kbo_odds.csv', index=False)
            print(f'  → {n}행 업데이트')

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)

# ── 최종 현황 ─────────────────────────────────────────────────────
print('\n======= 최종 현황 =======')
df2 = pd.read_csv('kbo_odds.csv')
g2  = pd.read_csv('kbo_games.csv')
for date in TARGET_DATES:
    print(f'\n=== {date} ===')
    d_g = g2[g2['date'] == date].sort_values('slot')
    d_df = df2[df2['date'] == date]
    for _, grow in d_g.iterrows():
        slot = grow['slot']
        s = d_df[d_df['slot'] == slot]
        wd_ok = s['winner_direction'].notna().sum()
        moved = s[s['home_open'].notna()].shape[0]
        print(f'  slot{int(slot)} {grow["home"]} vs {grow["away"]}  winner={grow["winner"]}  BM={len(s)}  변동={moved}  WD={wd_ok}')
