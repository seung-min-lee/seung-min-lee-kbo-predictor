"""
05-15 slot1-4에 누락된 BM 데이터만 추가 (기존 데이터 유지)
- 각 슬롯 페이지에서 현재 노출되는 BM 목록 파악
- DB에 없는 BM만 open+close 수집
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

GAMES = [
    ('2026-05-15', 1.0, 'Doosan Bears',  'Lotte Giants',  'Lotte Giants',  False, 'doosan-bears-lotte-giants-SQdZWvEj'),
    ('2026-05-15', 2.0, 'KT Wiz Suwon',  'Hanwha Eagles', 'Hanwha Eagles', False, 'kt-wiz-suwon-hanwha-eagles-tUM8ovTq'),
    ('2026-05-15', 3.0, 'Samsung Lions', 'KIA Tigers',    'KIA Tigers',    False, 'samsung-lions-kia-tigers-lWsUhMzA'),
    ('2026-05-15', 4.0, 'NC Dinos',      'Kiwoom Heroes', 'Kiwoom Heroes', False, 'nc-dinos-kiwoom-heroes-AoWxi05M'),
]

FAKE_BMS = {'My coupon', 'User Predictions'}


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-extensions')
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
            time.sleep(1)
            print('  쿠키 수락')
    except:
        pass


def load_page(driver, url, first=False):
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(4)
    except:
        time.sleep(4)
    if first:
        accept_cookies(driver)
        time.sleep(1)


def get_bm_names(driver):
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    return [n.text.strip() for n in name_els
            if n.text.strip() and n.text.strip() not in FAKE_BMS]


def parse_tooltip(driver):
    try:
        tooltip = driver.find_element(By.CSS_SELECTOR, 'div.tooltip.odds-tooltip')
        lines = [l.strip() for l in tooltip.text.split('\n') if l.strip()]
        open_val = close_val = None
        if 'Opening odds:' in lines:
            oi = lines.index('Opening odds:')
            if oi + 2 < len(lines):
                m = re.match(r'^(\d+\.\d+)$', lines[oi + 2])
                if m:
                    open_val = float(m.group(1))
        for line in lines[1:]:
            if line == 'Opening odds:':
                break
            if re.match(r'^\d+\.\d+$', line):
                close_val = float(line)
                break
        return open_val, close_val
    except:
        return None, None


def click_bm(driver, bm_name, side='home'):
    try:
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        target_el = None
        for nel in name_els:
            if nel.text.strip() == bm_name:
                target_el = nel
                break
        if not target_el:
            return None, None

        row = target_el
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        if len(odds_els) < 2:
            return None, None

        el = odds_els[0] if side == 'home' else odds_els[-1]
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-150);')
        time.sleep(0.4)
        ActionChains(driver).move_to_element(el).click().perform()
        time.sleep(2.5)
        return parse_tooltip(driver)
    except:
        return None, None


def calc_dir(ho, hc, ao, ac, wih):
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


def scrape_game(driver, date, slot, home, away, winner, wih, slug, existing_bms):
    url = BASE + slug + '/'
    match_id = slug.split('-')[-1]
    print(f'\n[{date} slot{int(slot)}] {home} vs {away}')
    print(f'  기존 BMs: {sorted(existing_bms)}')

    load_page(driver, url)
    bm_names = get_bm_names(driver)
    if not bm_names:
        print('  BMs 없음, 재시도...')
        load_page(driver, url)
        bm_names = get_bm_names(driver)

    new_bms = [b for b in bm_names if b not in existing_bms]
    print(f'  전체 BMs: {bm_names}')
    print(f'  추가 수집 BMs: {new_bms}')

    rows = []
    for bm in new_bms:
        load_page(driver, url)
        h_o, h_c = click_bm(driver, bm, 'home')
        load_page(driver, url)
        a_o, a_c = click_bm(driver, bm, 'away')

        print(f'  {bm:<20} h_o={h_o}  h_c={h_c}  a_o={a_o}  a_c={a_c}')
        if h_o is None and h_c is None and a_o is None and a_c is None:
            continue

        wd = calc_dir(h_o, h_c, a_o, a_c, wih)
        rows.append({
            'date': date, 'slot': slot, 'home': home, 'away': away,
            'match_id': match_id, 'bookmaker': bm,
            'home_open':   float(h_o) if h_o else float('nan'),
            'home_close':  float(h_c) if h_c else float('nan'),
            'away_open':   float(a_o) if a_o else float('nan'),
            'away_close':  float(a_c) if a_c else float('nan'),
            'home_change': round(h_c - h_o, 3) if h_o and h_c else float('nan'),
            'away_change': round(a_c - a_o, 3) if a_o and a_c else float('nan'),
            'winner': winner, 'winner_is_home': wih,
            'winner_direction': wd,
        })
    return rows


# ── 실행 ────────────────────────────────────────────────────────────────────
df = pd.read_csv('kbo_odds.csv')
print(f'시작: {len(df)}행')

driver = make_driver()
total_added = 0

try:
    first = True
    for date, slot, home, away, winner, wih, slug in GAMES:
        # 이 슬롯에 이미 있는 BM 목록
        mask = (df['date'] == date) & (df['slot'] == slot)
        existing_bms = set(df[mask]['bookmaker'].unique())

        rows = scrape_game(driver, date, slot, home, away, winner, wih, slug, existing_bms)
        if first and rows:
            accept_cookies(driver)
            first = False

        if rows:
            new_df = pd.DataFrame(rows)
            for col in df.columns:
                if col not in new_df.columns:
                    new_df[col] = float('nan')
            df = pd.concat([df, new_df[df.columns]], ignore_index=True)
            df.to_csv('kbo_odds.csv', index=False)
            print(f'  → {len(rows)}행 추가, 총 {len(df)}행 저장')
            total_added += len(rows)
        else:
            print('  → 추가 없음')

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print(f'\n=== 완료: 총 {total_added}행 추가 ===')

print('\n=== 05-15 slot1-4 최종 BM 현황 ===')
for slot in [1.0, 2.0, 3.0, 4.0]:
    s = df[(df['date'] == '2026-05-15') & (df['slot'] == slot)]
    bms = sorted(s['bookmaker'].unique())
    wd_ok = s['winner_direction'].notna().sum()
    print(f'  slot{int(slot)}: {len(bms)}BM, wd={wd_ok}/{len(s)}  → {bms}')
