import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, statistics, re, pandas as pd, numpy as np
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

BASE = 'https://www.oddsportal.com/baseball/south-korea/kbo/'

TARGETS = [
    # 05-08
    {'date':'2026-05-08','slot':1.0,'home':'Doosan Bears','away':'SSG Landers','match_id':'dO3C2Hoo',
     'bms':['Alphabet','GambleCity']},
    {'date':'2026-05-08','slot':2.0,'home':'Hanwha Eagles','away':'LG Twins','match_id':'CC3GKG7T',
     'bms':['bwin']},
    {'date':'2026-05-08','slot':3.0,'home':'Lotte Giants','away':'KIA Tigers','match_id':'z78iQKwh',
     'bms':['Kobet']},
    # 05-09
    {'date':'2026-05-09','slot':1.0,'home':'Doosan Bears','away':'SSG Landers','match_id':'UTqmFfVj',
     'bms':['BetInAsia','bwin','VOBET']},
    {'date':'2026-05-09','slot':3.0,'home':'Lotte Giants','away':'KIA Tigers','match_id':'MNWYxbNc',
     'bms':['1xBet','Momobet']},
]


def make_driver():
    opts = Options()
    opts.add_argument('--headless')
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
        return False


def get_popup_open(driver, bm_name, side='home'):
    try:
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        target = None
        for nel in name_els:
            if nel.text.strip() == bm_name:
                target = nel
                break
        if not target:
            return None

        row = target
        for _ in range(3):
            row = row.find_element(By.XPATH, '..')

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if not odds_els:
            odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
        if len(odds_els) < 2:
            return None

        el = odds_els[0] if side == 'home' else odds_els[-1]
        driver.execute_script('arguments[0].scrollIntoView(true);', el)
        driver.execute_script('window.scrollBy(0,-100);')
        time.sleep(0.3)
        driver.execute_script('arguments[0].click();', el)
        time.sleep(2)

        popup = driver.execute_script("""
            return document.querySelector("div[class*='fixed'][class*='height-content']");
        """)
        if not popup:
            return None

        text = driver.execute_script('return arguments[0].innerText;', popup)
        om = re.search(r'Opening odds:[\s\S]*?([\d.]{3,})', text)

        driver.execute_script('arguments[0].click();', el)
        time.sleep(0.5)

        return float(om.group(1)) if om else None
    except Exception as e:
        return None


def scrape_3times(driver, url, bm_name):
    h_opens, a_opens = [], []
    for attempt in range(3):
        if not load_page(driver, url):
            break
        h_o = get_popup_open(driver, bm_name, 'home')
        a_o = get_popup_open(driver, bm_name, 'away')
        print(f'    attempt{attempt+1}: h_open={h_o}, a_open={a_o}')
        if h_o is not None:
            h_opens.append(h_o)
        if a_o is not None:
            a_opens.append(a_o)

    result = {}
    if h_opens:
        result['home_open'] = statistics.median(h_opens)
        if len(h_opens) > 1 and max(h_opens) - min(h_opens) > 0.05:
            print(f'    ⚠ home_open 편차: {h_opens}')
    if a_opens:
        result['away_open'] = statistics.median(a_opens)
        if len(a_opens) > 1 and max(a_opens) - min(a_opens) > 0.05:
            print(f'    ⚠ away_open 편차: {a_opens}')
    return result


def calc_dir(row):
    if pd.isna(row['home_open']) or pd.isna(row['away_open']):
        return np.nan
    if pd.isna(row['winner_is_home']):
        return np.nan
    h_chg = row['home_close'] - row['home_open']
    a_chg = row['away_close'] - row['away_open']
    w_chg = h_chg if row['winner_is_home'] else a_chg
    l_chg = a_chg if row['winner_is_home'] else h_chg
    if abs(w_chg - l_chg) < 0.001:
        return np.nan
    return 1.0 if w_chg > l_chg else 0.0


df = pd.read_csv('kbo_odds.csv')
driver = make_driver()

try:
    for g in TARGETS:
        home_slug = g['home'].lower().replace(' ', '-')
        away_slug = g['away'].lower().replace(' ', '-')
        url = f"{BASE}{home_slug}-{away_slug}-{g['match_id']}/"
        print(f"\n[{g['date']} slot{int(g['slot'])}] {g['home']} vs {g['away']}")

        mask = (df['date'] == g['date']) & (df['slot'] == g['slot'])
        for bm in g['bms']:
            print(f"  BM: {bm}")
            pop = scrape_3times(driver, url, bm)
            bm_mask = mask & (df['bookmaker'] == bm)
            if not bm_mask.any():
                print(f"  → 행 없음")
                continue
            if 'home_open' in pop:
                df.loc[bm_mask, 'home_open'] = pop['home_open']
                print(f"  → home_open={pop['home_open']}")
            if 'away_open' in pop:
                df.loc[bm_mask, 'away_open'] = pop['away_open']
                print(f"  → away_open={pop['away_open']}")
            if not pop:
                print(f"  → 수집 실패")
finally:
    driver.quit()

# 재계산
for date in ['2026-05-08', '2026-05-09']:
    mask = df['date'] == date
    df.loc[mask, 'home_change'] = (df.loc[mask, 'home_close'] - df.loc[mask, 'home_open']).round(3)
    df.loc[mask, 'away_change'] = (df.loc[mask, 'away_close'] - df.loc[mask, 'away_open']).round(3)
    df.loc[mask, 'winner_direction'] = df[mask].apply(calc_dir, axis=1)

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 저장 완료 ===')
for date in ['2026-05-08', '2026-05-09']:
    mask = df['date'] == date
    n_open = df[mask]['home_open'].isna().sum()
    n_wd = df[mask]['winner_direction'].isna().sum()
    total = mask.sum()
    print(f'{date}: home_open NaN {n_open}/{total}, winner_direction NaN {n_wd}/{total}')
