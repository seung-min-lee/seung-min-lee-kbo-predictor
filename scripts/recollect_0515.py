"""2026-05-15 경기 배당 전체 재수집
recollect_range.py 로직 기반 — KBO results 페이지에서 정규 match URL 탐색
- close odds: 페이지 직접 읽기
- open odds: 팝업 스크래핑 (JS 클릭 우선)
- 기존 05-15 행 삭제 후 새 데이터로 교체
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import pandas as pd, time, glob as _glob

CSV_PATH = 'kbo_odds.csv'
EXCLUDE  = {'My coupon', 'User Predictions'}

TARGET_MATCHES = [
    {
        'match_id': 'SQdZWvEj', 'date': '2026-05-15', 'slot': 1.0,
        'home': 'Doosan Bears', 'away': 'Lotte Giants',
        'winner': 'Lotte Giants', 'wih': False,
        'home_score': 5.0, 'away_score': 6.0,
    },
    {
        'match_id': 'tUM8ovTq', 'date': '2026-05-15', 'slot': 2.0,
        'home': 'KT Wiz Suwon', 'away': 'Hanwha Eagles',
        'winner': 'Hanwha Eagles', 'wih': False,
        'home_score': 3.0, 'away_score': 5.0,
    },
    {
        'match_id': 'lWsUhMzA', 'date': '2026-05-15', 'slot': 3.0,
        'home': 'Samsung Lions', 'away': 'KIA Tigers',
        'winner': 'KIA Tigers', 'wih': False,
        'home_score': 4.0, 'away_score': 5.0,
    },
    {
        'match_id': 'AoWxi05M', 'date': '2026-05-15', 'slot': 4.0,
        'home': 'NC Dinos', 'away': 'Kiwoom Heroes',
        'winner': 'Kiwoom Heroes', 'wih': False,
        'home_score': 1.0, 'away_score': 4.0,
    },
    {
        'match_id': 'rZvMfr6c', 'date': '2026-05-15', 'slot': 5.0,
        'home': 'SSG Landers', 'away': 'LG Twins',
        'winner': 'LG Twins', 'wih': False,
        'home_score': 7.0, 'away_score': 8.0,
    },
]

# KBO results 페이지에서 match_id → 정규 URL 매핑
_result_urls = {}


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
        driver.execute_script("arguments[0].click();", odds_el)
        time.sleep(2.0)
        # fixed 팝업 확인 (static 패널과 구분)
        popup = driver.execute_script(
            "return document.querySelector('div[class*=\"fixed\"][class*=\"height-content\"]');")
        if not popup:
            ActionChains(driver).move_to_element(odds_el).click().perform()
            time.sleep(2.5)
    except:
        return None

    data = driver.execute_script("""
        // fixed position인 동적 팝업만 선택 (static bg-gray 패널 제외)
        const popup = document.querySelector('div[class*="fixed"][class*="height-content"]');
        if (!popup) return {openVal:null,closeVal:null,direction:null,change:null};

        const text = popup.innerText || '';
        let openVal=null, closeVal=null, direction=null, change=null;

        // "Opening odds:" 라벨 이후 첫 숫자
        const openMatch = text.match(/Opening\\s+odds[^\\d]*(\\d+\\.\\d+)/i);
        if (openMatch) openVal = parseFloat(openMatch[1]);

        // "Odds movement:" 또는 "Closing" 라벨 이후 첫 숫자
        const closeMatch = text.match(/(?:Odds\\s+movement|Closing)[^\\d]*(\\d+\\.\\d+)/i);
        if (closeMatch) closeVal = parseFloat(closeMatch[1]);

        // 라벨 없으면 font-bold 숫자 순서로 fallback
        if (!openVal || !closeVal) {
            const bolds = popup.querySelectorAll('.font-bold');
            const nums = [];
            for (const b of bolds) {
                const v = parseFloat(b.innerText);
                if (!isNaN(v) && v > 1.0 && v < 20) nums.push(v);
            }
            if (!openVal && nums.length >= 1) openVal = nums[0];
            if (!closeVal && nums.length >= 2) closeVal = nums[1];
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
                    "return document.querySelector('div[class*=\"fixed\"][class*=\"height-content\"]');"):
                break
            time.sleep(0.3)
    except:
        pass
    return data


def scrape_match(driver, url, wih):
    driver.get(url)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    except:
        print('  → 로딩 실패')
        return []
    time.sleep(4)

    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
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
        results.append({
            'bookmaker':      name,
            'home_open':      None,
            'home_close':     hc,
            'home_change':    None,
            'home_direction': None,
            'away_open':      None,
            'away_close':     ac,
            'away_change':    None,
            'away_direction': None,
            'winner_direction': None,
            'odds_ratio':     round(hc / ac, 4) if ac else None,
            'consensus':      'home' if hc < ac else 'away',
        })
        bm_order.append(name)

    print(f'  Close 읽기: {len(bm_order)}개 BM → open 팝업 수집 시작...')

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

            ho = results[i]['home_open']
            hc2 = results[i]['home_close']
            ao = results[i]['away_open']
            ac2 = results[i]['away_close']
            if ho and hc2 and ao and ac2:
                hchg = hc2 - ho
                achg = ac2 - ao
                wchg = hchg if wih else achg
                lchg = achg if wih else hchg
                if   lchg > wchg: results[i]['winner_direction'] = 1
                elif lchg < wchg: results[i]['winner_direction'] = 0

            print(f'    [{i+1}/{len(bm_order)}] {bm}: h_open={results[i]["home_open"]} '
                  f'a_open={results[i]["away_open"]} w_dir={results[i]["winner_direction"]}')
        except Exception as e:
            print(f'    [{i+1}] {bm} 실패: {e}')

    return results


def find_url(driver, match_id):
    """KBO results 페이지에서 match_id에 해당하는 정규 match URL 탐색"""
    if match_id in _result_urls:
        return _result_urls[match_id]

    results_url = 'https://www.oddsportal.com/baseball/south-korea/kbo/results/'
    driver.get(results_url)
    time.sleep(4)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(2)

    for page in range(3):
        links = driver.find_elements(By.CSS_SELECTOR, 'a[href]')
        for link in links:
            href = link.get_attribute('href') or ''
            if '#' not in href:
                continue
            mid = href.split('#')[-1]
            if len(mid) >= 6:
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

    url = _result_urls.get(match_id)
    if url:
        print(f'  URL 발견: {url}')
    else:
        print(f'  URL 탐색 실패 ({match_id})')
    return url


def main():
    df = pd.read_csv(CSV_PATH)
    print(f'기존 데이터: {len(df)}행')
    driver = get_driver()

    try:
        for m in TARGET_MATCHES:
            mid = m['match_id']
            print(f'\n[{m["date"]} Slot{int(m["slot"])}] {m["home"]} vs {m["away"]}')

            url = find_url(driver, mid)
            if not url:
                print('  → URL 없음, 스킵')
                continue

            rows = scrape_match(driver, url, m['wih'])
            if not rows:
                print('  → 데이터 없음, 스킵')
                continue

            df = df[df['match_id'] != mid]
            new_rows = [{
                'match_id':      mid,
                'date':          m['date'],
                'slot':          m['slot'],
                'home':          m['home'],
                'away':          m['away'],
                'winner':        m['winner'],
                'winner_is_home': m['wih'],
                'home_score':    m['home_score'],
                'away_score':    m['away_score'],
                **{k: r[k] for k in [
                    'bookmaker', 'home_open', 'home_close', 'home_change', 'home_direction',
                    'away_open', 'away_close', 'away_change', 'away_direction',
                    'winner_direction', 'odds_ratio', 'consensus'
                ]}
            } for r in rows]
            df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
            print(f'  → {len(rows)}행 저장')

            time.sleep(2)

    finally:
        driver.quit()

    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n저장 완료: {len(df)}행')

    chk = df[df['date'] == '2026-05-15'].groupby('slot').agg(
        bm_count=('bookmaker', 'count'),
        open_ok=('home_open', lambda x: x.notna().sum()),
        w_dir_ok=('winner_direction', lambda x: x.notna().sum())
    )
    print('\n05-15 슬롯별 결과:')
    print(chk)


if __name__ == '__main__':
    main()
