"""
과거/당일 경기 BM open/close 수집
- close: p.odds-text (전역, BM당 2개)
- open:  div.odds-cell 클릭 → odds-tooltip에서 'Opening odds:' 파싱
사용:
  python scripts/collect_bm_history.py  (05-21 재수집 + 05-22 신규)
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, json, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

GAMES_0521 = [
    (1.0, 'Doosan Bears',  'NC Dinos',      'Doosan Bears',  True,  'doosan-bears-nc-dinos-WjLiL2GU'),
    (2.0, 'Hanwha Eagles', 'Lotte Giants',  'Lotte Giants',  False, 'hanwha-eagles-lotte-giants-pfoRZ1VN'),
    (3.0, 'KIA Tigers',    'LG Twins',      'LG Twins',      False, 'kia-tigers-lg-twins-rVlAwpWb'),
    (4.0, 'Kiwoom Heroes', 'SSG Landers',   'Kiwoom Heroes', True,  'kiwoom-heroes-ssg-landers-jehIyO0B'),
    (5.0, 'Samsung Lions', 'KT Wiz Suwon',  'Samsung Lions', True,  'samsung-lions-kt-wiz-suwon-MF01u61n'),
]

TODAY_ODDS_PATH = 'kbo_today_odds.json'
FAKE_BMS = {'My coupon', 'User Predictions', 'Betfair Exchange'}


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--host-resolver-rules=MAP contentdeliverynetwork.cc 127.0.0.1, MAP *.contentdeliverynetwork.cc 127.0.0.1')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36')
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
            print('  쿠키 수락')
    except:
        pass


def load_page(driver, url, first=False):
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


def parse_val(s):
    m = re.findall(r'\d+\.\d+', str(s))
    return float(m[0]) if m else None


def get_open_from_tooltip(driver, cell_idx):
    """odds-cell 클릭 후 툴팁에서 Opening odds 파싱"""
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
                    m = re.findall(r'\d+\.\d+', lines[i + 2])
                    if m:
                        return float(m[0])
    except:
        pass
    return None


def scrape_bm_odds(driver, url, first=False):
    """
    close: p.odds-text 전역 추출 (BM당 2개: home, away)
    open:  각 odds-cell 클릭 → 툴팁 파싱
    반환: {bm: {home_open, home_close, away_open, away_close}}
    """
    load_page(driver, url, first=first)

    # BM 이름 추출
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    bm_names = [n.text.strip() for n in name_els
                if n.text.strip() and n.text.strip() not in FAKE_BMS]

    if not bm_names:
        print('  BM 없음')
        return {}

    # close 값 추출
    odds_els = driver.find_elements(By.CSS_SELECTOR, 'p.odds-text')
    close_vals = []
    for e in odds_els:
        v = parse_val(e.text.strip())
        if v is not None:
            close_vals.append(v)

    print(f'  BM {len(bm_names)}개 | close {len(close_vals)}개')

    if len(close_vals) < len(bm_names) * 2:
        print('  close 값 부족 - 재시도')
        time.sleep(3)
        odds_els = driver.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        close_vals = [parse_val(e.text.strip()) for e in odds_els]
        close_vals = [v for v in close_vals if v is not None]

    result = {}
    for i, bm in enumerate(bm_names):
        home_ci = i * 2
        away_ci = i * 2 + 1

        h_c = close_vals[home_ci] if home_ci < len(close_vals) else None
        a_c = close_vals[away_ci] if away_ci < len(close_vals) else None

        # open 값은 tooltip 클릭
        h_o = get_open_from_tooltip(driver, home_ci)
        a_o = get_open_from_tooltip(driver, away_ci)

        result[bm] = {
            'home_open':  h_o, 'home_close': h_c,
            'away_open':  a_o, 'away_close': a_c,
        }

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
        return 1.0 if lchg > wchg else 0.0
    except:
        return np.nan


def update_csv(df, date, slot, home, away, wih, bm_data, match_id=None):
    """bm_data를 kbo_odds.csv에 반영. 없는 행은 추가."""
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
            slug = match_id or ''
            mid  = slug.split('-')[-1] if '-' in str(slug) else slug
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
            if h_o is None:
                h_o = existing['home_open'] if pd.notna(existing.get('home_open')) else None
            if a_o is None:
                a_o = existing['away_open'] if pd.notna(existing.get('away_open')) else None
            if h_c is None:
                h_c = existing['home_close'] if pd.notna(existing.get('home_close')) else None
            if a_c is None:
                a_c = existing['away_close'] if pd.notna(existing.get('away_close')) else None

            if h_o is not None: df.loc[mask_bm, 'home_open']  = h_o
            if h_c is not None: df.loc[mask_bm, 'home_close'] = h_c
            if a_o is not None: df.loc[mask_bm, 'away_open']  = a_o
            if a_c is not None: df.loc[mask_bm, 'away_close'] = a_c

            if h_o and h_c:
                df.loc[mask_bm, 'home_change']    = round(h_c - h_o, 4)
                df.loc[mask_bm, 'home_direction'] = 1 if h_c < h_o else (-1 if h_c > h_o else 0)

            wd = calc_wd(h_o, h_c, a_o, a_c,
                         bool(existing.get('winner_is_home', wih)) if wih is None else wih)
            if not (isinstance(wd, float) and np.isnan(wd)):
                df.loc[mask_bm, 'winner_direction'] = wd

            updated += 1

    return df, updated


def get_0522_games():
    try:
        with open(TODAY_ODDS_PATH, encoding='utf-8') as f:
            tod = json.load(f)
    except:
        return []
    games = []
    for key, v in tod.items():
        if v.get('date') != '2026-05-22':
            continue
        url = v.get('match_url', '')
        slug = url.rstrip('/').split('/')[-1] if url else ''
        games.append({
            'slot':  float(v.get('slot', 0)),
            'home':  v['home'],
            'away':  v['away'],
            'slug':  slug,
            'url':   url,
        })
    games.sort(key=lambda x: x['slot'])
    return games


# ── 메인 ─────────────────────────────────────────────────────────
df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
first_load = True

try:
    # ── 05-21 재수집 ─────────────────────────────────────────────
    print('\n========== 05-21 BM 재수집 ==========')
    for slot, home, away, winner, wih, slug in GAMES_0521:
        url = BASE + slug + '/'
        print(f'\n[05-21 slot{int(slot)}] {home} vs {away}')
        bm_data = scrape_bm_odds(driver, url, first=first_load)
        first_load = False
        if not bm_data:
            print('  수집 실패')
            continue
        for bm, v in list(bm_data.items())[:3]:
            print(f'  {bm}: h_o={v["home_open"]} h_c={v["home_close"]}  a_o={v["away_open"]} a_c={v["away_close"]}')
        df, n = update_csv(df, '2026-05-21', slot, home, away, wih, bm_data)
        df.to_csv('kbo_odds.csv', index=False)
        print(f'  → {n}행 업데이트')

    # ── 05-22 수집 ─────────────────────────────────────────────
    print('\n========== 05-22 BM 수집 ==========')
    games_22 = get_0522_games()
    if not games_22:
        print('kbo_today_odds.json에 05-22 경기 없음')
    for g in games_22:
        url  = g['url']
        home = g['home']
        away = g['away']
        slot = g['slot']
        slug = g['slug']
        if not url:
            print(f'  slot{int(slot)} URL 없음 - 스킵')
            continue
        print(f'\n[05-22 slot{int(slot)}] {home} vs {away}')
        bm_data = scrape_bm_odds(driver, url)
        if not bm_data:
            print('  수집 실패')
            continue
        for bm, v in list(bm_data.items())[:3]:
            print(f'  {bm}: h_o={v["home_open"]} h_c={v["home_close"]}  a_o={v["away_open"]} a_c={v["away_close"]}')
        df, n = update_csv(df, '2026-05-22', slot, home, away, None, bm_data, match_id=slug)
        df.to_csv('kbo_odds.csv', index=False)
        print(f'  → {n}행 업데이트')

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)

# ── 최종 현황 ─────────────────────────────────────────────────────
for date in ['2026-05-21', '2026-05-22']:
    d = df[df['date'] == date]
    if d.empty:
        continue
    print(f'\n=== {date} BM 현황 ===')
    for (home, away), g in d.groupby(['home', 'away']):
        wd_ok  = g['winner_direction'].notna().sum()
        moved  = ((g['home_open'] != g['home_close']) & g['home_open'].notna()).sum()
        print(f'  {home} vs {away}: {len(g)}BM | 변동:{moved} | WD:{wd_ok}')
