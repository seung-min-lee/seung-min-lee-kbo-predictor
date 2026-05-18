"""05-06 경기 배당 재수집 (open 포함) - 독립 실행 스크립트"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import pandas as pd, time, os, glob as _glob

CSV_PATH = 'kbo_odds.csv'
EXCLUDE  = {'My coupon', 'User Predictions'}

TARGET_MATCHES = [
    {'match_id': 'p2TPt1PO', 'slot': 1.0, 'home': 'LG Twins',      'away': 'Doosan Bears',  'winner': 'LG Twins',      'wih': True},
    {'match_id': '4Cqae0vI', 'slot': 2.0, 'home': 'KIA Tigers',    'away': 'Hanwha Eagles', 'winner': 'Hanwha Eagles', 'wih': False},
    {'match_id': 'zXirarug', 'slot': 3.0, 'home': 'Samsung Lions', 'away': 'Kiwoom Heroes', 'winner': 'Samsung Lions', 'wih': True},
    {'match_id': 'WboicM95', 'slot': 4.0, 'home': 'KT Wiz Suwon', 'away': 'Lotte Giants',  'winner': 'Lotte Giants',  'wih': False},
    {'match_id': 'lGgz14At', 'slot': 5.0, 'home': 'SSG Landers',  'away': 'NC Dinos',      'winner': 'SSG Landers',   'wih': True},
]

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    cached = _glob.glob(os.path.join(os.path.expanduser('~'), '.wdm', 'drivers',
                        'chromedriver', '**', 'chromedriver.exe'), recursive=True)
    from selenium.webdriver.chrome.service import Service
    path = sorted(cached)[-1] if cached else None
    if path is None:
        from webdriver_manager.chrome import ChromeDriverManager
        path = ChromeDriverManager().install()
    driver = webdriver.Chrome(service=Service(path), options=options)
    driver.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def scrape_team_odds(driver, odds_el):
    """클릭 팝업에서 open/close/direction/change 수집"""
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", odds_el)
        driver.execute_script("window.scrollBy(0,-150);")
        time.sleep(0.5)
        ActionChains(driver).move_to_element(odds_el).click().perform()
        time.sleep(3.0)
    except:
        return None

    data = driver.execute_script("""
        const popup = document.querySelector('div.height-content[class*="bg-gray-med_light"]');
        if (!popup) return {openVal:null,closeVal:null,direction:null,change:null};
        let openVal=null, closeVal=null, direction=null, change=null;
        const openSection = popup.querySelector('div[class*="mt-2"]');
        if (openSection) {
            const boldEls = openSection.querySelectorAll('.font-bold');
            for (const b of boldEls) {
                const v = parseFloat(b.innerText);
                if (!isNaN(v) && v > 1) { openVal = v; break; }
            }
        }
        const rowDiv = popup.querySelector('.flex.flex-row');
        if (rowDiv) {
            const cols = rowDiv.querySelectorAll(':scope > div');
            if (cols.length > 1) {
                const boldEl = cols[1].querySelector('.font-bold');
                if (boldEl) {
                    const v = parseFloat(boldEl.innerText);
                    if (!isNaN(v) && v > 1) closeVal = v;
                }
            }
        }
        if (openVal && closeVal && openVal !== closeVal) {
            direction = closeVal > openVal ? 1 : 0;
            change = (closeVal - openVal).toFixed(2);
        }
        return {openVal, closeVal, direction, change};
    """)

    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        for _ in range(5):
            if not driver.execute_script(
                    "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');"):
                break
            time.sleep(0.3)
    except:
        pass
    return data

def find_url_by_match_id(driver, match_id):
    """결과 페이지에서 match_id로 실제 경기 URL 탐색"""
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    time.sleep(4)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)
    links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/h2h/"]')
    for link in links:
        href = link.get_attribute('href') or ''
        if match_id in href:
            return href
    return None

def scrape_match_with_open(driver, match_id, winner_is_home):
    url = find_url_by_match_id(driver, match_id)
    if not url:
        print(f'  → URL 탐색 실패 ({match_id})')
        return []
    print(f'  URL: {url}')
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    except:
        print('  → 로딩 실패')
        return []
    time.sleep(3)

    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    results, bm_order = [], []

    for name_el in name_els:
        name = name_el.text.strip()
        if not name or name in EXCLUDE:
            continue
        try:
            row = name_el
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if len(odds_els) < 2:
                continue
            home_close = float(odds_els[0].text.strip())
            away_close = float(odds_els[-1].text.strip())
        except:
            continue

        results.append({
            'bookmaker':       name,
            'home_open':       None, 'home_close':  home_close,
            'home_change':     None, 'home_direction': None,
            'away_open':       None, 'away_close':  away_close,
            'away_change':     None, 'away_direction': None,
            'winner_direction':None,
            'odds_ratio':      round(home_close / away_close, 4) if away_close else None,
            'consensus':       'home' if home_close < away_close else 'away',
        })
        bm_order.append(name)

    print(f'  Pass1: {len(bm_order)}개 BM, open 수집 시작...')

    for i, bm in enumerate(bm_order):
        try:
            name_els2 = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
            target = next((el for el in name_els2 if el.text.strip() == bm), None)
            if not target:
                continue
            row = target
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if len(odds_els) < 2:
                continue

            h = scrape_team_odds(driver, odds_els[0])
            a = scrape_team_odds(driver, odds_els[-1])

            if h:
                results[i]['home_open']      = h.get('openVal')
                results[i]['home_close']     = h.get('closeVal') or results[i]['home_close']
                results[i]['home_change']    = h.get('change')
                results[i]['home_direction'] = h.get('direction')
            if a:
                results[i]['away_open']      = a.get('openVal')
                results[i]['away_close']     = a.get('closeVal') or results[i]['away_close']
                results[i]['away_change']    = a.get('change')
                results[i]['away_direction'] = a.get('direction')

            ho, hc = results[i]['home_open'], results[i]['home_close']
            ao, ac = results[i]['away_open'], results[i]['away_close']
            if ho and hc and ao and ac:
                hchg = hc - ho
                achg = ac - ao
                wchg = hchg if winner_is_home else achg
                lchg = achg if winner_is_home else hchg
                if wchg > lchg:
                    results[i]['winner_direction'] = 1
                elif wchg < lchg:
                    results[i]['winner_direction'] = 0

            print(f'    [{i+1}/{len(bm_order)}] {bm}: h_open={results[i]["home_open"]} a_open={results[i]["away_open"]} w_dir={results[i]["winner_direction"]}')
        except Exception as e:
            print(f'    실패 ({bm}): {e}')

    return results

def main():
    df = pd.read_csv(CSV_PATH)
    driver = get_driver()

    try:
        for m in TARGET_MATCHES:
            mid, slot, home, away = m['match_id'], m['slot'], m['home'], m['away']
            winner, wih = m['winner'], m['wih']
            print(f'\n[Slot {int(slot)}] {home} vs {away}')
            rows = scrape_match_with_open(driver, mid, wih)
            print(f'  → 총 {len(rows)}행')
            if not rows:
                continue

            df = df[df['match_id'] != mid]
            new_rows = [{
                'match_id': mid, 'date': '2026-05-06', 'slot': slot,
                'home': home, 'away': away, 'winner': winner, 'winner_is_home': wih,
                'home_score': None, 'away_score': None,
                **{k: r[k] for k in ['bookmaker','home_open','home_close','home_change',
                   'home_direction','away_open','away_close','away_change','away_direction',
                   'winner_direction','odds_ratio','consensus']},
            } for r in rows]
            df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    finally:
        driver.quit()

    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n저장 완료: {len(df)}행')

    df2 = pd.read_csv(CSV_PATH)
    chk = df2[df2['date']=='2026-05-06'].drop_duplicates('match_id')[
        ['slot','home','away','home_open','away_open','winner_direction']]
    print('\n05-06 수집 결과:')
    print(chk.to_string())

if __name__ == '__main__':
    main()
