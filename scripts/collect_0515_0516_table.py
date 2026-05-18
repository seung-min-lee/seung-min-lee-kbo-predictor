"""
05-15, 05-16 close odds — OddsPortal match 페이지 테이블 수집
현재 OddsPortal에 보이는 BM들의 close(현재표시) 배당을 긁어 kbo_odds.csv 업데이트
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

GAMES = [
    ('2026-05-15', 1.0, 'Doosan Bears',  'Lotte Giants',  'Lotte Giants',  False, 'doosan-bears-lotte-giants-SQdZWvEj'),
    ('2026-05-15', 2.0, 'KT Wiz Suwon', 'Hanwha Eagles', 'Hanwha Eagles', False, 'kt-wiz-suwon-hanwha-eagles-tUM8ovTq'),
    ('2026-05-15', 3.0, 'Samsung Lions', 'KIA Tigers',    'KIA Tigers',    False, 'samsung-lions-kia-tigers-lWsUhMzA'),
    ('2026-05-15', 4.0, 'NC Dinos',      'Kiwoom Heroes', 'Kiwoom Heroes', False, 'nc-dinos-kiwoom-heroes-AoWxi05M'),
    ('2026-05-15', 5.0, 'SSG Landers',   'LG Twins',      'LG Twins',      False, 'ssg-landers-lg-twins-rZvMfr6c'),
    ('2026-05-16', 1.0, 'KT Wiz Suwon', 'Hanwha Eagles', 'Hanwha Eagles', False, 'kt-wiz-suwon-hanwha-eagles-S0DrbHCk'),
    ('2026-05-16', 2.0, 'Doosan Bears',  'Lotte Giants',  'Doosan Bears',  True,  'doosan-bears-lotte-giants-Aonqhgqt'),
    ('2026-05-16', 3.0, 'Samsung Lions', 'KIA Tigers',    'Samsung Lions', True,  'samsung-lions-kia-tigers-z3Y35aKF'),
    ('2026-05-16', 4.0, 'NC Dinos',      'Kiwoom Heroes', 'NC Dinos',      True,  'nc-dinos-kiwoom-heroes-rTyC3wkS'),
    ('2026-05-16', 5.0, 'SSG Landers',   'LG Twins',      'SSG Landers',   True,  'ssg-landers-lg-twins-Uk337Lk3'),
]


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


def scrape_table(driver, slug):
    """match 페이지에서 BM별 배당 수집 (close = 현재 표시값)"""
    url = f"{BASE}{slug}/"
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(4)
    except:
        time.sleep(4)

    FAKE_BMS = {'My coupon', 'User Predictions'}
    result = {}
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    for nel in name_els:
        bm = nel.text.strip()
        if not bm or bm in FAKE_BMS:
            continue
        try:
            row = nel
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if not odds_els:
                odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
            if len(odds_els) >= 2:
                h = float(odds_els[0].text.strip().replace(',', '.'))
                a = float(odds_els[-1].text.strip().replace(',', '.'))
                if 1.01 <= h <= 15 and 1.01 <= a <= 15:
                    result[bm] = {'home': h, 'away': a}
        except:
            pass
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


df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
updated = 0
new_rows_added = 0

try:
    for date, slot, home, away, winner, wih, slug in GAMES:
        print(f"\n[{date} slot{int(slot)}] {home} vs {away}")
        mask = (df['date'] == date) & (df['slot'] == slot)
        match_id = slug.split('-')[-1]

        page_data = scrape_table(driver, slug)
        print(f"  페이지 BM {len(page_data)}개: {list(page_data.keys())}")

        for bm, vals in page_data.items():
            hc_new = vals['home']
            ac_new = vals['away']

            bm_mask = mask & (df['bookmaker'] == bm)

            if any(bm_mask):
                # 기존 행 업데이트
                row = df.loc[bm_mask].iloc[0]
                ho = row['home_open']
                ao = row['away_open']

                # 이미 close 있고 값이 합리적이면 스킵 (단 slot1 05-16 제외 - 라이브배당)
                existing_hc = row['home_close']
                if pd.notna(existing_hc) and not (date == '2026-05-16' and slot == 1.0):
                    # 이미 유효한 close가 있으면 스킵
                    continue

                df.loc[bm_mask, 'home_close'] = hc_new
                df.loc[bm_mask, 'away_close'] = ac_new
                if pd.notna(ho): df.loc[bm_mask, 'home_change'] = round(hc_new - float(ho), 3)
                if pd.notna(ao): df.loc[bm_mask, 'away_change'] = round(ac_new - float(ao), 3)
                df.loc[bm_mask, 'winner_direction'] = calc_dir(ho, hc_new, ao, ac_new, wih)
                wd = df.loc[bm_mask, 'winner_direction'].iloc[0]
                print(f"  ✓ {bm}: hc={hc_new} ac={ac_new} wd={wd}")
                updated += 1
            else:
                # 새 BM — open 없으므로 close만 있는 행 추가 (open=NaN, wd=NaN)
                new_row = {
                    'date': date, 'slot': slot, 'home': home, 'away': away,
                    'match_id': match_id, 'bookmaker': bm,
                    'home_open': float('nan'), 'home_close': hc_new,
                    'away_open': float('nan'), 'away_close': ac_new,
                    'home_change': float('nan'), 'away_change': float('nan'),
                    'winner': winner, 'winner_is_home': wih,
                    'winner_direction': float('nan'),
                }
                for col in df.columns:
                    if col not in new_row:
                        new_row[col] = float('nan')
                df = pd.concat([df, pd.DataFrame([new_row])[df.columns]], ignore_index=True)
                print(f"  + {bm}: 신규행 추가 (open없음→wd=NaN)")
                new_rows_added += 1

        df.to_csv('kbo_odds.csv', index=False)

finally:
    driver.quit()

print(f'\n=== 완료: {updated}건 업데이트, {new_rows_added}건 신규 ===')
print()
for date in ['2026-05-15', '2026-05-16']:
    d = df[df['date'] == date]
    for slot in sorted(d['slot'].unique()):
        s = d[d['slot'] == slot]
        wd_ok = s['winner_direction'].notna().sum()
        close_ok = s['home_close'].notna().sum()
        print(f'{date} slot{int(slot)}: close={close_ok}/{len(s)}, wd={wd_ok}/{len(s)}')
