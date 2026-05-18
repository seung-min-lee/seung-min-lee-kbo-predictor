"""
05-16 누락 close odds 재수집 (OddsPortal popup)
대상:
- slot1 KT vs Hanwha: 전체 13BM (라이브배당→NaN)
- slot3 Samsung vs KIA: 5BM 누락
- slot4 NC vs Kiwoom: 2BM 누락
- slot5 SSG vs LG: 1BM 누락
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, statistics, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

DATE = '2026-05-16'
BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

TARGETS = [
    {'slot': 1.0, 'home': 'KT Wiz Suwon',  'away': 'Hanwha Eagles',
     'match_id': 'kt-wiz-suwon-hanwha-eagles-S0DrbHCk',
     'bms': ['10x10bet','1xBet','22Bet','Alphabet','BetInAsia','Cloudbet','GambleCity','Kobet','Melbet','Momobet','Stake.com','VOBET','bwin']},
    {'slot': 3.0, 'home': 'Samsung Lions',  'away': 'KIA Tigers',
     'match_id': 'samsung-lions-kia-tigers-z3Y35aKF',
     'bms': ['10x10bet','Alphabet','GambleCity','VOBET','bwin']},
    {'slot': 4.0, 'home': 'NC Dinos',       'away': 'Kiwoom Heroes',
     'match_id': 'nc-dinos-kiwoom-heroes-rTyC3wkS',
     'bms': ['Stake.com','bwin']},
    {'slot': 5.0, 'home': 'SSG Landers',    'away': 'LG Twins',
     'match_id': 'ssg-landers-lg-twins-Uk337Lk3',
     'bms': ['bwin']},
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


def load_page(driver, url):
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(5)
        return True
    except:
        # 페이지는 로드됐지만 BM rows 없을 수도 있음
        time.sleep(3)
        return False


def get_popup_odds(driver, bm_name, side='home'):
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
        driver.execute_script('window.scrollBy(0,-100);')
        time.sleep(0.3)
        driver.execute_script('arguments[0].click();', el)
        time.sleep(2)

        popup = driver.execute_script(
            "return document.querySelector(\"div[class*='fixed'][class*='height-content']\");")
        if not popup:
            return None, None

        text = driver.execute_script('return arguments[0].innerText;', popup)
        om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)
        cm = re.search(r'Closing odds:[\s\S]*?([\d.]{3,})', text)
        if not cm:
            cm = re.search(r'Odds movement:[\s\S]*?([\d.]{3,})', text)

        # 팝업 닫기
        driver.execute_script('arguments[0].click();', el)
        time.sleep(0.4)

        open_val = float(om.group(1)) if om else None
        close_val = float(cm.group(1)) if cm else None
        return open_val, close_val
    except Exception as e:
        return None, None


def scrape_bm(driver, url, bm_name):
    h_opens, h_closes, a_opens, a_closes = [], [], [], []
    for attempt in range(3):
        ok = load_page(driver, url)
        if not ok and attempt == 2:
            break
        h_o, h_c = get_popup_odds(driver, bm_name, 'home')
        a_o, a_c = get_popup_odds(driver, bm_name, 'away')
        print(f'    attempt{attempt+1}: h_open={h_o} h_close={h_c} | a_open={a_o} a_close={a_c}')
        if h_o is not None: h_opens.append(h_o)
        if h_c is not None: h_closes.append(h_c)
        if a_o is not None: a_opens.append(a_o)
        if a_c is not None: a_closes.append(a_c)

    result = {}
    if h_opens: result['home_open'] = statistics.median(h_opens)
    if h_closes: result['home_close'] = statistics.median(h_closes)
    if a_opens: result['away_open'] = statistics.median(a_opens)
    if a_closes: result['away_close'] = statistics.median(a_closes)
    return result


def calc_dir(ho, hc, ao, ac, wih):
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [ho, hc, ao, ac]):
            return np.nan
        if wih is None:
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
success = fail = 0

try:
    for target in TARGETS:
        slot = target['slot']
        home = target['home']
        away = target['away']
        url = f"{BASE}{target['match_id']}/"
        print(f"\n[slot{int(slot)}] {home} vs {away}")
        print(f"  URL: {url}")

        mask = (df['date'] == DATE) & (df['slot'] == slot)
        wih_row = df[mask].dropna(subset=['winner_is_home'])
        wih = bool(wih_row.iloc[0]['winner_is_home']) if not wih_row.empty else None

        # 팝업 사용 가능 여부 먼저 테스트
        load_page(driver, url)
        bm_rows = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        if not bm_rows:
            print(f"  ⚠ BM rows 없음 - popup 미지원 (경기 후 {1}일, 아직 인덱싱 전)")
            continue
        print(f"  ✓ {len(bm_rows)}개 BM row 발견")

        for bm in target['bms']:
            print(f"  BM: {bm}")
            pop = scrape_bm(driver, url, bm)

            bm_mask = mask & (df['bookmaker'] == bm)
            if not any(bm_mask):
                print(f"    → CSV에 해당 BM 행 없음")
                continue

            if pop:
                if 'home_close' in pop:
                    df.loc[bm_mask, 'home_close'] = pop['home_close']
                if 'away_close' in pop:
                    df.loc[bm_mask, 'away_close'] = pop['away_close']
                if 'home_open' in pop and df.loc[bm_mask, 'home_open'].isna().any():
                    df.loc[bm_mask, 'home_open'] = pop['home_open']
                if 'away_open' in pop and df.loc[bm_mask, 'away_open'].isna().any():
                    df.loc[bm_mask, 'away_open'] = pop['away_open']

                # 재계산
                r = df.loc[bm_mask].iloc[0]
                ho, hc = r['home_open'], r['home_close']
                ao, ac = r['away_open'], r['away_close']
                if all(pd.notna([ho, hc, ao, ac])):
                    df.loc[bm_mask, 'home_change'] = round(float(hc) - float(ho), 3)
                    df.loc[bm_mask, 'away_change'] = round(float(ac) - float(ao), 3)
                df.loc[bm_mask, 'winner_direction'] = calc_dir(ho, hc, ao, ac, wih)
                wd = df.loc[bm_mask, 'winner_direction'].iloc[0]
                print(f"    → h:{ho}→{pop.get('home_close','?')} a:{ao}→{pop.get('away_close','?')} wd={wd}")
                success += 1
            else:
                print(f"    → 팝업 실패")
                fail += 1

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print(f'\n=== 완료: 성공 {success}건 / 실패 {fail}건 ===')

# 최종 현황
print()
for date in ['2026-05-15', '2026-05-16']:
    d = df[df['date'] == date]
    for slot in sorted(d['slot'].unique()):
        s = d[d['slot'] == slot]
        wd_ok = s['winner_direction'].notna().sum()
        total = len(s)
        print(f'{date} slot{int(slot)}: wd={wd_ok}/{total}')
