"""지정 기간 경기 배당 재수집 (open/close/direction 포함)"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import pandas as pd, time, os, glob as _glob, threading

CSV_PATH = 'kbo_odds.csv'
EXCLUDE  = {'My coupon', 'User Predictions'}

TARGET_MATCHES = [
  {"match_id":"8OdBucr3","date":"2026-05-02","slot":1.0,"home":"SSG Landers","away":"Lotte Giants","winner":"Lotte Giants","wih":False},
  {"match_id":"fLUbWh5k","date":"2026-05-02","slot":2.0,"home":"Kiwoom Heroes","away":"Doosan Bears","winner":"Kiwoom Heroes","wih":True},
  {"match_id":"4jjKwyDF","date":"2026-05-02","slot":3.0,"home":"Samsung Lions","away":"Hanwha Eagles","winner":"Hanwha Eagles","wih":False},
  {"match_id":"AmgSyFsS","date":"2026-05-02","slot":4.0,"home":"KIA Tigers","away":"KT Wiz Suwon","winner":"KIA Tigers","wih":True},
  {"match_id":"GU9PHgjd","date":"2026-05-02","slot":5.0,"home":"LG Twins","away":"NC Dinos","winner":"LG Twins","wih":True},
  {"match_id":"S2zYrWle","date":"2026-05-03","slot":1.0,"home":"Kiwoom Heroes","away":"Doosan Bears","winner":"Doosan Bears","wih":False},
  {"match_id":"j7E1jEdL","date":"2026-05-03","slot":2.0,"home":"Samsung Lions","away":"Hanwha Eagles","winner":"Samsung Lions","wih":True},
  {"match_id":"KxXPphKr","date":"2026-05-03","slot":3.0,"home":"KIA Tigers","away":"KT Wiz Suwon","winner":"KT Wiz Suwon","wih":False},
  {"match_id":"2oY6UWZ1","date":"2026-05-03","slot":4.0,"home":"LG Twins","away":"NC Dinos","winner":"NC Dinos","wih":False},
  {"match_id":"IgGghzS8","date":"2026-05-03","slot":5.0,"home":"SSG Landers","away":"Lotte Giants","winner":"Lotte Giants","wih":False},
  {"match_id":"lIOtsAJ7","date":"2026-05-05","slot":1.0,"home":"LG Twins","away":"Doosan Bears","winner":"LG Twins","wih":True},
  {"match_id":"xxQHrNfC","date":"2026-05-05","slot":2.0,"home":"KIA Tigers","away":"Hanwha Eagles","winner":"KIA Tigers","wih":True},
  {"match_id":"8dY0n5em","date":"2026-05-05","slot":3.0,"home":"Samsung Lions","away":"Kiwoom Heroes","winner":"Samsung Lions","wih":True},
  {"match_id":"tAW8pqQa","date":"2026-05-05","slot":4.0,"home":"KT Wiz Suwon","away":"Lotte Giants","winner":"KT Wiz Suwon","wih":True},
  {"match_id":"p2TPt1PO","date":"2026-05-06","slot":1.0,"home":"LG Twins","away":"Doosan Bears","winner":"LG Twins","wih":True},
  {"match_id":"4Cqae0vI","date":"2026-05-06","slot":2.0,"home":"KIA Tigers","away":"Hanwha Eagles","winner":"Hanwha Eagles","wih":False},
  {"match_id":"zXirarug","date":"2026-05-06","slot":3.0,"home":"Samsung Lions","away":"Kiwoom Heroes","winner":"Samsung Lions","wih":True},
  {"match_id":"WboicM95","date":"2026-05-06","slot":4.0,"home":"KT Wiz Suwon","away":"Lotte Giants","winner":"Lotte Giants","wih":False},
  {"match_id":"lGgz14At","date":"2026-05-06","slot":5.0,"home":"SSG Landers","away":"NC Dinos","winner":"SSG Landers","wih":True},
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
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", odds_el)
        driver.execute_script("window.scrollBy(0,-150);")
        time.sleep(0.5)
        # JS 클릭 먼저 시도 (headless에서 ActionChains보다 안정적)
        driver.execute_script("arguments[0].click();", odds_el)
        time.sleep(1.5)
        # 팝업이 안 열리면 ActionChains 재시도
        popup = driver.execute_script(
            "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');")
        if not popup:
            ActionChains(driver).move_to_element(odds_el).click().perform()
            time.sleep(2.5)
    except:
        return None
    data = driver.execute_script("""
        const popup = document.querySelector('div.height-content[class*="bg-gray-med_light"]');
        if (!popup) return {openVal:null,closeVal:null,direction:null,change:null};
        let openVal=null, closeVal=null, direction=null, change=null;

        // open: 팝업 전체에서 첫 번째 유효 숫자 (mt-2 이전 영역)
        const allBolds = popup.querySelectorAll('.font-bold');
        for (const b of allBolds) {
            const v = parseFloat(b.innerText);
            if (!isNaN(v) && v > 1) { openVal = v; break; }
        }

        // close: mt-2 섹션의 첫 번째 유효 숫자
        const mtSection = popup.querySelector('div[class*="mt-2"]');
        if (mtSection) {
            for (const b of mtSection.querySelectorAll('.font-bold')) {
                const v = parseFloat(b.innerText);
                if (!isNaN(v) && v > 1) { closeVal = v; break; }
            }
        }
        // mt-2 없으면 두 번째 숫자를 close로
        if (!closeVal) {
            let cnt = 0;
            for (const b of allBolds) {
                const v = parseFloat(b.innerText);
                if (!isNaN(v) && v > 1) {
                    cnt++;
                    if (cnt === 2) { closeVal = v; break; }
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
            if not driver.execute_script("return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');"):
                break
            time.sleep(0.3)
    except:
        pass
    return data

# 결과 페이지 URL 캐시
_result_urls = {}

def safe_get(driver, url, timeout=90):
    t = threading.Thread(target=lambda: driver.get(url), daemon=True)
    t.start()
    t.join(timeout)

def find_url(driver, match_id):
    if match_id in _result_urls:
        return _result_urls[match_id]
    safe_get(driver, 'https://www.oddsportal.com/baseball/south-korea/kbo/results/', 60)
    time.sleep(3)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)
    # 페이지 2까지 탐색
    for page in range(2):
        for link in driver.find_elements(By.CSS_SELECTOR, 'a[href*="/h2h/"]'):
            href = link.get_attribute('href') or ''
            if '#' in href:
                mid = href.split('#')[-1]
                _result_urls[mid] = href
        if match_id in _result_urls:
            break
        btn = driver.execute_script("""
            const cur = document.querySelector('a[data-number].active');
            if (!cur) return null;
            const n = parseInt(cur.getAttribute('data-number'));
            return [...document.querySelectorAll('a[data-number]')]
                .find(b => parseInt(b.getAttribute('data-number')) === n+1) || null;
        """)
        if not btn:
            break
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(3)
    return _result_urls.get(match_id)

def scrape_match_with_open(driver, url, wih):
    safe_get(driver, url, 60)
    time.sleep(5)

    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    if not name_els:
        print('  → 로딩 실패 (BM 없음)')
        return []
    results, bm_order = [], []
    for nel in name_els:
        name = nel.text.strip()
        if not name or name in EXCLUDE:
            continue
        try:
            row = nel
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if len(odds_els) < 2:
                continue
            hc = float(odds_els[0].text.strip())
            ac = float(odds_els[-1].text.strip())
        except:
            continue
        results.append({'bookmaker': name, 'home_open': None, 'home_close': hc,
                        'home_change': None, 'home_direction': None,
                        'away_open': None, 'away_close': ac,
                        'away_change': None, 'away_direction': None,
                        'winner_direction': None,
                        'odds_ratio': round(hc/ac, 4) if ac else None,
                        'consensus': 'home' if hc < ac else 'away'})
        bm_order.append(name)

    print(f'  Pass1: {len(bm_order)}개 BM → open 수집...')
    for i, bm in enumerate(bm_order):
        try:
            nels2 = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
            tgt = next((el for el in nels2 if el.text.strip() == bm), None)
            if not tgt:
                continue
            row = tgt
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
            ho, hc2 = results[i]['home_open'], results[i]['home_close']
            ao, ac2 = results[i]['away_open'], results[i]['away_close']
            if ho and hc2 and ao and ac2:
                hchg = hc2 - ho
                achg = ac2 - ao
                wchg = hchg if wih else achg
                lchg = achg if wih else hchg
                if lchg > wchg:   results[i]['winner_direction'] = 1
                elif lchg < wchg: results[i]['winner_direction'] = 0
            print(f'    [{i+1}/{len(bm_order)}] {bm}: h_open={results[i]["home_open"]} w_dir={results[i]["winner_direction"]}')
        except Exception as e:
            print(f'    [{i+1}] {bm} 실패: {e}')
    return results

def main():
    df = pd.read_csv(CSV_PATH)
    driver = get_driver()

    try:
        for m in TARGET_MATCHES:
            mid = m['match_id']
            print(f'\n[{m["date"]} Slot{int(m["slot"])}] {m["home"]} vs {m["away"]}')
            url = find_url(driver, mid)
            if not url:
                print(f'  URL 탐색 실패 ({mid})')
                continue
            print(f'  {url}')
            rows = scrape_match_with_open(driver, url, m['wih'])
            if not rows:
                continue
            df = df[df['match_id'] != mid]
            new_rows = [{'match_id': mid, 'date': m['date'], 'slot': m['slot'],
                         'home': m['home'], 'away': m['away'],
                         'winner': m['winner'], 'winner_is_home': m['wih'],
                         'home_score': None, 'away_score': None, **{k: r[k] for k in [
                             'bookmaker','home_open','home_close','home_change','home_direction',
                             'away_open','away_close','away_change','away_direction',
                             'winner_direction','odds_ratio','consensus']}} for r in rows]
            df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
            print(f'  → {len(rows)}행 저장')
    finally:
        driver.quit()

    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n저장 완료: {len(df)}행')

    df2 = pd.read_csv(CSV_PATH)
    mask = (df2['date'] >= '2026-05-02') & (df2['date'] <= '2026-05-06')
    chk = df2[mask].groupby('date')['winner_direction'].apply(lambda x: x.isna().sum())
    print('\n날짜별 winner_direction 누락:')
    print(chk)

if __name__ == '__main__':
    main()
