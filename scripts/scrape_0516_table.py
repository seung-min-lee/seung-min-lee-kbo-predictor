"""
05-16 close odds - match 페이지 테이블에서 직접 수집 (팝업 없이)
대상: slot1 전체, slot3/4/5 일부 BM
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

DATE = '2026-05-16'
BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

TARGETS = [
    {'slot': 1.0, 'home': 'KT Wiz Suwon',  'away': 'Hanwha Eagles',
     'url': 'kt-wiz-suwon-hanwha-eagles-S0DrbHCk',
     'bms': None},  # None = 전체 BM
    {'slot': 3.0, 'home': 'Samsung Lions',  'away': 'KIA Tigers',
     'url': 'samsung-lions-kia-tigers-z3Y35aKF',
     'bms': ['10x10bet','Alphabet','GambleCity','VOBET','bwin']},
    {'slot': 4.0, 'home': 'NC Dinos',       'away': 'Kiwoom Heroes',
     'url': 'nc-dinos-kiwoom-heroes-rTyC3wkS',
     'bms': ['Stake.com','bwin']},
    {'slot': 5.0, 'home': 'SSG Landers',    'away': 'LG Twins',
     'url': 'ssg-landers-lg-twins-Uk337Lk3',
     'bms': ['bwin']},
]

BM_ALIASES = {
    '10x10bet': ['10x10bet', '10X10Bet'],
    '1xBet':    ['1xBet', '1XBET'],
    '22Bet':    ['22Bet', '22BET'],
    'Alphabet': ['Alphabet'],
    'BetInAsia':['BetInAsia'],
    'Bets.io':  ['Bets.io'],
    'Cloudbet': ['Cloudbet'],
    'GambleCity':['GambleCity'],
    'Kobet':    ['Kobet'],
    'Melbet':   ['Melbet'],
    'Momobet':  ['Momobet'],
    'Roobet':   ['Roobet'],
    'Stake.com':['Stake.com'],
    'VOBET':    ['VOBET'],
    'bwin':     ['bwin'],
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


def load_and_scrape(driver, url):
    """페이지 로드 후 BM별 배당 수집"""
    full_url = f"{BASE}{url}/"
    driver.get(full_url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(4)
    except:
        time.sleep(5)

    results = {}
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    print(f"  BM rows: {len(name_els)}")

    for nel in name_els:
        bm_name = nel.text.strip()
        if not bm_name:
            continue

        try:
            row = nel
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')

            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if not odds_els:
                odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')

            if len(odds_els) >= 2:
                try:
                    home_val = float(odds_els[0].text.strip().replace(',','.'))
                    away_val = float(odds_els[-1].text.strip().replace(',','.'))
                    results[bm_name] = {'home': home_val, 'away': away_val}
                except:
                    pass
        except:
            pass

    return results


def calc_dir(ho, hc, ao, ac, wih):
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(float(v)))
               for v in [ho, hc, ao, ac]):
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


df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
updated = 0

try:
    for target in TARGETS:
        slot = target['slot']
        home = target['home']
        away = target['away']
        target_bms = target['bms']

        print(f"\n[slot{int(slot)}] {home} vs {away}")
        mask = (df['date'] == DATE) & (df['slot'] == slot)

        wih_rows = df[mask].dropna(subset=['winner_is_home'])
        wih = bool(wih_rows.iloc[0]['winner_is_home']) if not wih_rows.empty else None

        page_odds = load_and_scrape(driver, target['url'])
        print(f"  수집된 BMs: {list(page_odds.keys())}")

        for page_bm, odds_val in page_odds.items():
            # 내부 BM명과 매핑
            canonical = None
            for k, aliases in BM_ALIASES.items():
                if any(page_bm.lower() == a.lower() for a in aliases):
                    canonical = k
                    break
            if canonical is None:
                canonical = page_bm

            if target_bms is not None and canonical not in target_bms:
                continue

            bm_mask = mask & (df['bookmaker'] == canonical)
            if not any(bm_mask):
                # 새 BM이면 스킵
                continue

            row = df.loc[bm_mask].iloc[0]
            ho = row['home_open']
            ao = row['away_open']
            hc_new = odds_val['home']
            ac_new = odds_val['away']

            # 유효성 검사 (close 값이 너무 크면 라이브배당)
            if hc_new > 10 or ac_new > 10:
                print(f"  ⚠ {canonical}: close h={hc_new} a={ac_new} → 라이브배당 의심, 스킵")
                continue

            df.loc[bm_mask, 'home_close'] = hc_new
            df.loc[bm_mask, 'away_close'] = ac_new
            if pd.notna(ho) and pd.notna(ao):
                df.loc[bm_mask, 'home_change'] = round(float(hc_new) - float(ho), 3)
                df.loc[bm_mask, 'away_change'] = round(float(ac_new) - float(ao), 3)
            df.loc[bm_mask, 'winner_direction'] = calc_dir(ho, hc_new, ao, ac_new, wih)
            wd = df.loc[bm_mask, 'winner_direction'].iloc[0]
            print(f"  ✓ {canonical}: h_close={hc_new} a_close={ac_new} wd={wd}")
            updated += 1

        # 중간 저장
        df.to_csv('kbo_odds.csv', index=False)

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print(f'\n=== 완료: {updated}건 업데이트 ===')

print()
for slot_n in [1, 3, 4, 5]:
    s = df[(df['date'] == DATE) & (df['slot'] == slot_n)]
    wd_ok = s['winner_direction'].notna().sum()
    total = len(s)
    print(f"  slot{slot_n}: wd={wd_ok}/{total}")
