"""
05-16 경기 close odds 테이블 수집 → home_close/away_close 보완 → movement 계산
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

GAMES_0516 = [
    (1.0, 'KT Wiz Suwon',  'Hanwha Eagles', 'Hanwha Eagles', False, 'kt-wiz-suwon-hanwha-eagles-S0DrbHCk'),
    (2.0, 'Doosan Bears',  'Lotte Giants',  'Doosan Bears',  True,  'doosan-bears-lotte-giants-Aonqhgqt'),
    (3.0, 'Samsung Lions', 'KIA Tigers',    'Samsung Lions', True,  'samsung-lions-kia-tigers-z3Y35aKF'),
    (4.0, 'NC Dinos',      'Kiwoom Heroes', 'NC Dinos',      True,  'nc-dinos-kiwoom-heroes-rTyC3wkS'),
    (5.0, 'SSG Landers',   'LG Twins',      'SSG Landers',   True,  'ssg-landers-lg-twins-Uk337Lk3'),
]

FAKE_BMS = {'My coupon', 'User Predictions'}


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


def accept_cookies(driver):
    try:
        btn = driver.find_element(By.CSS_SELECTOR, '#onetrust-accept-btn-handler')
        if btn.is_displayed():
            driver.execute_script('arguments[0].click();', btn)
            time.sleep(1)
    except:
        pass


def scrape_table(driver, url, first=False):
    """테이블에서 home_close, away_close 수집"""
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
                try:
                    hc = float(odds_els[0].text.strip())
                    ac = float(odds_els[-1].text.strip())
                    result[bm] = (hc, ac)
                except:
                    pass
        except:
            pass
    return result


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
        return 1.0 if wchg > lchg else 0.0
    except:
        return np.nan


df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
updated = 0

try:
    for i, (slot, home, away, winner, wih, slug) in enumerate(GAMES_0516):
        url = BASE + slug + '/'
        print('\n[2026-05-16 slot%d] %s vs %s' % (int(slot), home, away))

        close_data = scrape_table(driver, url, first=(i == 0))
        print('  수집: %d BM' % len(close_data))

        mask = (df['date'] == '2026-05-16') & (df['slot'] == slot)

        for bm, (hc, ac) in close_data.items():
            bm_mask = mask & (df['bookmaker'] == bm)
            if not any(bm_mask):
                continue

            row = df[bm_mask].iloc[0]
            cur_hc = row['home_close']
            cur_ac = row['away_close']

            # close가 없거나 NaN인 경우에만 업데이트
            if pd.isna(cur_hc) or pd.isna(cur_ac):
                df.loc[bm_mask, 'home_close'] = hc
                df.loc[bm_mask, 'away_close'] = ac
                # home_change, away_change 갱신
                ho = row['home_open']
                ao = row['away_open']
                if not pd.isna(ho):
                    df.loc[bm_mask, 'home_change'] = round(float(hc) - float(ho), 3)
                if not pd.isna(ao):
                    df.loc[bm_mask, 'away_change'] = round(float(ac) - float(ao), 3)
                # winner_direction 재계산
                wd = calc_dir(ho, hc, ao, ac, wih)
                if not (isinstance(wd, float) and np.isnan(wd)):
                    df.loc[bm_mask, 'winner_direction'] = wd
                print('  + %s: h_close=%.2f a_close=%.2f wd=%s' % (bm, hc, ac, wd))
                updated += 1
            else:
                # 이미 있으면 movement만 재계산
                ho = row['home_open']
                ao = row['away_open']
                if not pd.isna(ho) and pd.isna(row.get('winner_direction', float('nan'))):
                    wd = calc_dir(ho, cur_hc, ao, cur_ac, wih)
                    if not (isinstance(wd, float) and np.isnan(wd)):
                        df.loc[bm_mask, 'winner_direction'] = wd

        df.to_csv('kbo_odds.csv', index=False)
        print('  → 저장')

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 완료: close 보완 %d개 ===' % updated)

for slot in [1.0, 2.0, 3.0, 4.0, 5.0]:
    s = df[(df['date'] == '2026-05-16') & (df['slot'] == slot)]
    if s.empty:
        continue
    print('05-16 slot%d: %dBM open=%d close=%d wd=%d' % (
        int(slot), len(s),
        s['home_open'].notna().sum(),
        s['home_close'].notna().sum(),
        s['winner_direction'].notna().sum()))
