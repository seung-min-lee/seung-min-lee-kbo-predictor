"""
05-21 경기 BM별 Opening/Closing odds 팝업 수집 → kbo_odds.csv 업데이트
각 BM 배당 클릭 → Opening odds / Closing odds 파싱 → winner_direction 계산
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

# (slot, home, away, winner, winner_is_home, slug)
GAMES_0521 = [
    (1.0, 'Doosan Bears',  'NC Dinos',      'Doosan Bears',  True,  'doosan-bears-nc-dinos-WjLiL2GU'),
    (2.0, 'Hanwha Eagles', 'Lotte Giants',  'Lotte Giants',  False, 'hanwha-eagles-lotte-giants-pfoRZ1VN'),
    (3.0, 'KIA Tigers',    'LG Twins',      'LG Twins',      False, 'kia-tigers-lg-twins-rVlAwpWb'),
    (4.0, 'Kiwoom Heroes', 'SSG Landers',   'Kiwoom Heroes', True,  'kiwoom-heroes-ssg-landers-jehIyO0B'),
    (5.0, 'Samsung Lions', 'KT Wiz Suwon',  'Samsung Lions', True,  'samsung-lions-kt-wiz-suwon-MF01u61n'),
]

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
            time.sleep(1)
            print('  쿠키 수락')
    except:
        pass


def load_page(driver, url, first=False):
    driver.get(url)
    try:
        WebDriverWait(driver, 25).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(3)
    except:
        time.sleep(4)
    if first:
        accept_cookies(driver)
        time.sleep(1)


def parse_odds_val(text):
    m = re.findall(r'\d+\.\d+', text)
    return float(m[-1]) if m else None


def get_popup_odds(driver, bm_name, side='home'):
    """BM 배당 클릭 → Opening/Closing odds 파싱"""
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

        open_val = close_val = None
        try:
            open_label = driver.find_element(By.XPATH, "//div[text()='Opening odds:']")
            open_sib = open_label.find_element(By.XPATH, 'following-sibling::*[1]')
            open_val = parse_odds_val(open_sib.text)
        except:
            pass
        try:
            close_label = driver.find_element(By.XPATH, "//div[text()='Closing odds:']")
            close_sib = close_label.find_element(By.XPATH, 'following-sibling::*[1]')
            close_val = parse_odds_val(close_sib.text)
        except:
            pass

        return open_val, close_val
    except:
        return None, None


def scrape_game(driver, url, first_game=False):
    """한 경기 전체 BM open/close 수집"""
    load_page(driver, url, first=first_game)
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    bm_names = [n.text.strip() for n in name_els
                if n.text.strip() and n.text.strip() not in FAKE_BMS]
    if not bm_names:
        print('  BM rows 없음')
        return {}
    print(f'  BM {len(bm_names)}개: {bm_names[:5]}...')

    result = {}
    for bm in bm_names:
        load_page(driver, url)
        h_o, h_c = get_popup_odds(driver, bm, 'home')

        load_page(driver, url)
        a_o, a_c = get_popup_odds(driver, bm, 'away')

        r = {}
        if h_o is not None: r['home_open']  = h_o
        if h_c is not None: r['home_close'] = h_c
        if a_o is not None: r['away_open']  = a_o
        if a_c is not None: r['away_close'] = a_c
        if r:
            result[bm] = r
        print(f'  {bm}: h_o={h_o} h_c={h_c} a_o={a_o} a_c={a_c}')

    return result


def calc_winner_direction(ho, hc, ao, ac, wih):
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


df = pd.read_csv('kbo_odds.csv')
driver = make_driver()
updated = 0

try:
    for i, (slot, home, away, winner, wih, slug) in enumerate(GAMES_0521):
        url = BASE + slug + '/'
        match_id = slug.split('-')[-1]
        print(f'\n[2026-05-21 slot{int(slot)}] {home} vs {away}')

        bm_results = scrape_game(driver, url, first_game=(i == 0))
        if not bm_results:
            print('  수집 실패')
            continue

        mask_game = (df['date'] == '2026-05-21') & (df['slot'] == slot)

        for bm, vals in bm_results.items():
            mask_bm = mask_game & (df['bookmaker'] == bm)
            ho = vals.get('home_open')
            hc = vals.get('home_close')
            ao = vals.get('away_open')
            ac = vals.get('away_close')

            if not any(mask_bm):
                # 새 행 추가
                if hc is None or ac is None:
                    continue
                new_row = {
                    'match_id': match_id, 'date': '2026-05-21', 'slot': slot,
                    'home': home, 'away': away, 'winner': winner,
                    'winner_is_home': wih,
                    'bookmaker': bm,
                    'home_open': ho, 'home_close': hc,
                    'home_change': round(hc - ho, 4) if ho else None,
                    'home_direction': (1 if hc < ho else (-1 if hc > ho else 0)) if ho else None,
                    'away_open': ao, 'away_close': ac,
                    'away_change': round(ac - ao, 4) if ao else None,
                    'away_direction': None,
                    'winner_direction': calc_winner_direction(ho, hc, ao, ac, wih),
                    'odds_ratio': round(hc / ac, 4) if ac else None,
                    'consensus': 'home' if hc < ac else 'away',
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                updated += 1
            else:
                # 기존 행 업데이트
                if ho is not None:
                    df.loc[mask_bm, 'home_open'] = ho
                if hc is not None:
                    df.loc[mask_bm, 'home_close'] = hc
                if ao is not None:
                    df.loc[mask_bm, 'away_open'] = ao
                if ac is not None:
                    df.loc[mask_bm, 'away_close'] = ac
                if ho and hc:
                    df.loc[mask_bm, 'home_change'] = round(hc - ho, 4)
                    df.loc[mask_bm, 'home_direction'] = 1 if hc < ho else (-1 if hc > ho else 0)
                wd = calc_winner_direction(ho, hc, ao, ac, wih)
                if not (isinstance(wd, float) and np.isnan(wd)):
                    df.loc[mask_bm, 'winner_direction'] = wd
                updated += 1

        df.to_csv('kbo_odds.csv', index=False)
        print(f'  → 저장 완료')

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print(f'\n=== 완료: {updated}행 업데이트 ===')

print('\n=== 05-21 BM 최종 현황 ===')
d21 = df[df['date'] == '2026-05-21']
for (home, away), g in d21.groupby(['home', 'away']):
    wd_ok = g['winner_direction'].notna().sum()
    moved = ((g['home_open'] != g['home_close']) & g['home_open'].notna()).sum()
    print(f'  {home} vs {away}: {len(g)}BM | 변동:{moved} | winner_direction:{wd_ok}')
