"""
05-15 전체 삭제 후 현재 OddsPortal 8개 BM open+close 재수집
popup 구조: "ODDS MOVEMENT\n[close_date]\n[close_val]\n[change]\nOpening odds:\n[open_date]\n[open_val]"
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
    ('2026-05-15', 5.0, 'SSG Landers',   'LG Twins',      'LG Twins',      False, 'ssg-landers-lg-twins-rZvMfr6c'),
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


def parse_tooltip(driver):
    """div.tooltip.odds-tooltip 텍스트에서 open, close 파싱
    구조: ODDS MOVEMENT / [close_date] / [close_val] / [change] / Opening odds: / [open_date] / [open_val]
    """
    try:
        tooltip = driver.find_element(By.CSS_SELECTOR, 'div.tooltip.odds-tooltip')
        lines = [l.strip() for l in tooltip.text.split('\n') if l.strip()]
        open_val = close_val = None

        # Opening odds: 다음 두 번째 항목이 값
        if 'Opening odds:' in lines:
            oi = lines.index('Opening odds:')
            if oi + 2 < len(lines):
                m = re.match(r'^(\d+\.\d+)$', lines[oi + 2])
                if m:
                    open_val = float(m.group(1))

        # close = "ODDS MOVEMENT" 이후 ~ "Opening odds:" 전 첫 번째 소수
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
    """BM 배당 클릭 후 tooltip 파싱. 리로드는 호출 전에 완료되어 있어야 함."""
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
        return 1.0 if wchg > lchg else 0.0
    except:
        return np.nan


# ── 실행 ──────────────────────────────────────────────────────────────────────
df = pd.read_csv('kbo_odds.csv')
before = len(df)
df = df[df['date'] != '2026-05-15'].reset_index(drop=True)
df.to_csv('kbo_odds.csv', index=False)
print('05-15 삭제: %d → %d행' % (before, len(df)))

driver = make_driver()
added = 0

try:
    for i, (date, slot, home, away, winner, wih, slug) in enumerate(GAMES):
        url = BASE + slug + '/'
        match_id = slug.split('-')[-1]
        print('\n[%s slot%d] %s vs %s' % (date, int(slot), home, away))

        # BM 목록 파악 (첫 로드)
        load_page(driver, url, first=(i == 0))
        # 로딩 재시도 (BM 없을 경우 한 번 더)
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        bm_names = [n.text.strip() for n in name_els
                    if n.text.strip() and n.text.strip() not in FAKE_BMS]
        if not bm_names:
            print('  BMs 없음, 재시도...')
            load_page(driver, url)
            name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
            bm_names = [n.text.strip() for n in name_els
                        if n.text.strip() and n.text.strip() not in FAKE_BMS]
        print('  BMs: %s' % bm_names)

        for bm in bm_names:
            # home 클릭
            load_page(driver, url)
            h_o, h_c = click_bm(driver, bm, 'home')

            # away 클릭
            load_page(driver, url)
            a_o, a_c = click_bm(driver, bm, 'away')

            print('  %-20s h_o=%-5s h_c=%-5s a_o=%-5s a_c=%-5s' % (
                bm, h_o, h_c, a_o, a_c))

            if h_o is None and h_c is None:
                continue

            wd = calc_dir(h_o, h_c, a_o, a_c, wih)
            new_row = {
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
            }
            for col in df.columns:
                if col not in new_row:
                    new_row[col] = float('nan')
            df = pd.concat([df, pd.DataFrame([new_row])[df.columns]], ignore_index=True)
            added += 1

        df.to_csv('kbo_odds.csv', index=False)
        print('  → 저장 (%d행)' % len(df))

finally:
    driver.quit()

df.to_csv('kbo_odds.csv', index=False)
print('\n=== 완료: 추가 %d행 ===' % added)

for slot in [1.0, 2.0, 3.0, 4.0, 5.0]:
    s = df[(df['date'] == '2026-05-15') & (df['slot'] == slot)]
    if s.empty:
        continue
    print('05-15 slot%d: %dBM open=%d close=%d wd=%d' % (
        int(slot), len(s),
        s['home_open'].notna().sum(),
        s['home_close'].notna().sum(),
        s['winner_direction'].notna().sum()))
