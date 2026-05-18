"""
05-15, 05-16 BM open/close 팝업 수집 → kbo_odds.csv 삽입
실행 조건: 경기 후 3일 이상 (05-19 이후 실행)
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, statistics, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

GAMES = [
    # (date, slot, home, away, match_id_slug)
    ('2026-05-15', 1.0, 'Doosan Bears',   'Lotte Giants',   'doosan-bears-lotte-giants-SQdZWvEj'),
    ('2026-05-15', 2.0, 'KT Wiz Suwon',  'Hanwha Eagles',  'kt-wiz-suwon-hanwha-eagles-tUM8ovTq'),
    ('2026-05-15', 3.0, 'Samsung Lions',  'KIA Tigers',     'samsung-lions-kia-tigers-lWsUhMzA'),
    ('2026-05-15', 4.0, 'NC Dinos',       'Kiwoom Heroes',  'nc-dinos-kiwoom-heroes-AoWxi05M'),
    ('2026-05-15', 5.0, 'SSG Landers',    'LG Twins',       'ssg-landers-lg-twins-rZvMfr6c'),
    ('2026-05-16', 1.0, 'KT Wiz Suwon',  'Hanwha Eagles',  'kt-wiz-suwon-hanwha-eagles-S0DrbHCk'),
    ('2026-05-16', 2.0, 'Doosan Bears',   'Lotte Giants',   'doosan-bears-lotte-giants-Aonqhgqt'),
    ('2026-05-16', 3.0, 'Samsung Lions',  'KIA Tigers',     'samsung-lions-kia-tigers-z3Y35aKF'),
    ('2026-05-16', 4.0, 'NC Dinos',       'Kiwoom Heroes',  'nc-dinos-kiwoom-heroes-rTyC3wkS'),
    ('2026-05-16', 5.0, 'SSG Landers',    'LG Twins',       'ssg-landers-lg-twins-Uk337Lk3'),
]

# 경기별 결과 (kbo_games.csv에서 확인된 값)
RESULTS = {
    ('2026-05-15', 1.0): ('Lotte Giants',  False),
    ('2026-05-15', 2.0): ('Hanwha Eagles', False),
    ('2026-05-15', 3.0): ('KIA Tigers',    False),
    ('2026-05-15', 4.0): ('Kiwoom Heroes', False),
    ('2026-05-15', 5.0): ('LG Twins',      False),
    ('2026-05-16', 1.0): ('Hanwha Eagles', False),
    ('2026-05-16', 2.0): ('Doosan Bears',  True),
    ('2026-05-16', 3.0): ('Samsung Lions', True),
    ('2026-05-16', 4.0): ('NC Dinos',      True),
    ('2026-05-16', 5.0): ('SSG Landers',   True),
}


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


def load_page(driver, url):
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(4)
        return True
    except:
        time.sleep(3)
        return False


def get_popup(driver, bm_name, side='home'):
    try:
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        target = None
        for nel in name_els:
            if nel.text.strip() == bm_name:
                target = nel; break
        if not target:
            return None, None

        row = target
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        if len(odds_els) < 2:
            return None, None

        el = odds_els[0] if side == 'home' else odds_els[-1]
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-100);')
        time.sleep(0.3)
        driver.execute_script('arguments[0].click();', el)
        time.sleep(2)

        popup = driver.execute_script(
            "return document.querySelector(\"div[class*='fixed'][class*='height-content']\");")
        if not popup:
            driver.execute_script('arguments[0].click();', el)
            time.sleep(0.3)
            return None, None

        text = driver.execute_script('return arguments[0].innerText;', popup)
        om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)
        cm = re.search(r'Closing odds:[\s\S]*?([\d.]{3,})', text)
        if not cm:
            cm = re.search(r'Odds movement:[\s\S]*?([\d.]{3,})', text)

        driver.execute_script('arguments[0].click();', el)
        time.sleep(0.3)

        return (float(om.group(1)) if om else None,
                float(cm.group(1)) if cm else None)
    except:
        return None, None


def scrape_game(driver, url):
    """한 경기의 전체 BM open/close 수집 (3회 시도, 중앙값)"""
    bm_data = {}  # {bm: {h_opens, h_closes, a_opens, a_closes}}

    for attempt in range(3):
        if not load_page(driver, url):
            continue

        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        bm_names = [nel.text.strip() for nel in name_els if nel.text.strip()]

        for bm in bm_names:
            if bm not in bm_data:
                bm_data[bm] = {'ho': [], 'hc': [], 'ao': [], 'ac': []}
            h_o, h_c = get_popup(driver, bm, 'home')
            a_o, a_c = get_popup(driver, bm, 'away')
            if h_o: bm_data[bm]['ho'].append(h_o)
            if h_c: bm_data[bm]['hc'].append(h_c)
            if a_o: bm_data[bm]['ao'].append(a_o)
            if a_c: bm_data[bm]['ac'].append(a_c)

    result = {}
    for bm, vals in bm_data.items():
        r = {}
        if vals['ho']: r['home_open']  = statistics.median(vals['ho'])
        if vals['hc']: r['home_close'] = statistics.median(vals['hc'])
        if vals['ao']: r['away_open']  = statistics.median(vals['ao'])
        if vals['ac']: r['away_close'] = statistics.median(vals['ac'])
        if r:
            result[bm] = r
    return result


def calc_dir(ho, hc, ao, ac, wih):
    try:
        if any(v is None or np.isnan(float(v)) for v in [ho, hc, ao, ac]):
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


# ── 실행 ────────────────────────────────────────────────────────────
df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
new_rows = []

try:
    for date, slot, home, away, slug in GAMES:
        url = f"{BASE}{slug}/"
        winner, wih = RESULTS[(date, slot)]
        match_id = slug.split('-')[-1]

        print(f"\n[{date} slot{int(slot)}] {home} vs {away}")

        # 이미 데이터 있으면 스킵
        existing = df[(df['date'] == date) & (df['slot'] == slot)]
        if not existing.empty:
            print(f"  이미 {len(existing)}행 존재 → 스킵")
            continue

        bm_results = scrape_game(driver, url)
        print(f"  수집 BM: {list(bm_results.keys())}")

        for bm, vals in bm_results.items():
            ho = vals.get('home_open')
            hc = vals.get('home_close')
            ao = vals.get('away_open')
            ac = vals.get('away_close')

            if ho is None and hc is None:
                continue

            hchg = round(float(hc) - float(ho), 3) if ho and hc else float('nan')
            achg = round(float(ac) - float(ao), 3) if ao and ac else float('nan')
            wd = calc_dir(ho, hc, ao, ac, wih)

            new_rows.append({
                'date': date, 'slot': slot, 'home': home, 'away': away,
                'match_id': match_id, 'bookmaker': bm,
                'home_open':  float(ho) if ho else float('nan'),
                'home_close': float(hc) if hc else float('nan'),
                'away_open':  float(ao) if ao else float('nan'),
                'away_close': float(ac) if ac else float('nan'),
                'home_change': hchg, 'away_change': achg,
                'winner': winner, 'winner_is_home': wih,
                'winner_direction': wd,
            })

        # 경기 단위 중간 저장
        if new_rows:
            new_df = pd.DataFrame(new_rows)
            for col in df.columns:
                if col not in new_df.columns:
                    new_df[col] = float('nan')
            new_df = new_df[df.columns]
            df = pd.concat([df, new_df], ignore_index=True)
            df.to_csv('kbo_odds.csv', index=False)
            new_rows = []
            print(f"  → 저장 완료 ({len(bm_results)}BM)")

finally:
    driver.quit()

print(f'\n=== 완료 ===')
print(f'kbo_odds.csv: {len(df)}행')

for date in ['2026-05-15', '2026-05-16']:
    d = df[df['date'] == date]
    if d.empty:
        print(f'{date}: 데이터 없음')
        continue
    for slot in sorted(d['slot'].unique()):
        s = d[d['slot'] == slot]
        wd_ok = s['winner_direction'].notna().sum()
        print(f'{date} slot{int(slot)}: {wd_ok}/{len(s)} wd')
