from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time, os
from datetime import datetime as _dt, timedelta as _td

def normalize_date(raw):
    """'Today, 25 Apr' / 'Yesterday, 24 Apr' / '21 Apr 2026' → 'YYYY-MM-DD'"""
    s = str(raw).strip()
    today = _dt.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        return (today - _td(days=1)).strftime('%Y-%m-%d')
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return _dt.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s

EXCLUDE  = {'My coupon', 'User Predictions'}
CSV_PATH = 'kbo_odds.csv'

def get_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])

    if os.environ.get('CI'):
        from selenium.webdriver.chrome.service import Service
        options.binary_location = '/usr/bin/chromium-browser'
        driver = webdriver.Chrome(
            service=Service('/usr/bin/chromedriver'), options=options)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options)

    driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def get_match_urls(driver):
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    time.sleep(3)
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
    time.sleep(3)

    match_list = driver.execute_script("""
        const results=[], seen=new Set();
        let currentDate='';
        document.querySelectorAll('div.eventRow').forEach(row=>{
            const dateEl=row.querySelector('[data-testid="date-header"]');
            if(dateEl&&dateEl.innerText.trim()) currentDate=dateEl.innerText.trim();
            const link=row.querySelector('a[href*="/h2h/"]');
            if(!link) return;
            const href=link.href;
            if(!href.includes('#')||seen.has(href)) return;
            seen.add(href);
            const teams=[...row.querySelectorAll('p.participant-name')]
                .map(el=>el.innerText.trim()).filter(Boolean).slice(0,2);
            const nums=[...row.querySelectorAll('[data-v-115522af]')]
                .map(el=>el.innerText.trim()).filter(t=>/^\\d+$/.test(t));
            const homeScore=parseInt(nums[0]);
            const awayScore=parseInt(nums[2]);
            results.push({
                date:currentDate, url:href,
                match_id:href.split('#')[1],
                home:teams[0]||'', away:teams[1]||'',
                home_score:homeScore||0, away_score:awayScore||0,
                winner_is_home:homeScore>awayScore,
                finished:!isNaN(homeScore)&&!isNaN(awayScore)&&homeScore!==awayScore
            });
        });
        return results;
    """)

    date_counter = {}
    for m in match_list:
        d = m['date']
        date_counter[d] = date_counter.get(d, 0) + 1
        m['slot'] = date_counter[d]
    return match_list

def scrape_team_odds(driver, odds_el):
    """특정 팀 배당 클릭 후 open/close/direction/change 수집"""
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", odds_el)
        driver.execute_script("window.scrollBy(0,-100);")
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", odds_el)
        time.sleep(2.0)
    except:
        return None

    data = driver.execute_script("""
        const panels=document.querySelectorAll('.bg-gray-light');
        let openVal=null,closeVal=null,direction=null,change=null;
        for(const panel of panels){
            const h1=panel.querySelector('h1');
            if(h1){
                const ce=panel.querySelector('.text-green-dark,.text-red-dark');
                if(ce){
                    change=ce.innerText.trim();
                    direction=ce.classList.contains('text-green-dark')?1:0;
                }
                for(const el of panel.querySelectorAll('.font-bold')){
                    const v=parseFloat(el.innerText);
                    if(!isNaN(v)&&v>1){closeVal=v;break;}
                }
            }else{
                for(const el of panel.querySelectorAll('.font-bold')){
                    const v=parseFloat(el.innerText);
                    if(!isNaN(v)&&v>1){openVal=v;break;}
                }
            }
        }
        if(direction===null&&openVal&&closeVal&&openVal!==closeVal){
            direction=closeVal>openVal?1:0;
            change=(closeVal-openVal).toFixed(2);
        }
        return{openVal,closeVal,direction,change};
    """)

    # 패널 닫기
    try:
        driver.execute_script("arguments[0].click();", odds_el)
        for _ in range(5):
            if driver.execute_script(
                "return document.querySelectorAll('.bg-gray-light').length;") <= 2:
                break
            time.sleep(0.3)
    except:
        pass

    return data

def scrape_match(driver, url, winner_is_home=True):
    """한 경기의 모든 북메이커 closing 배당 수집 (open/direction은 UI 변경으로 None)"""
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    except:
        print('  → 로딩 실패')
        return []
    time.sleep(3)

    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    results = []

    for name_el in name_els:
        name = name_el.text.strip()
        if name in EXCLUDE or not name:
            continue

        try:
            row = name_el
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
        except:
            continue

        odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
        if len(odds_els) < 2:
            continue

        try:
            home_close = float(odds_els[0].text.strip())
            away_close = float(odds_els[-1].text.strip())
        except (ValueError, IndexError):
            continue

        odds_ratio = round(home_close / away_close, 4) if away_close else None
        consensus = 'home' if home_close < away_close else 'away'

        results.append({
            'match_id':         url.split('#')[-1],
            'bookmaker':        name,
            'home_open':        None,
            'home_close':       home_close,
            'home_change':      None,
            'home_direction':   None,
            'away_open':        None,
            'away_close':       away_close,
            'away_change':      None,
            'away_direction':   None,
            'winner_direction': None,
            'odds_ratio':       odds_ratio,
            'consensus':        consensus,
        })

    return results

# ── 메인 ──────────────────────────────────────────────
driver  = get_driver()
new_rows = []

try:
    if os.path.exists(CSV_PATH):
        existing    = pd.read_csv(CSV_PATH)
        existing_ids = set(existing['match_id'].unique())
        print(f'기존 데이터: {len(existing)}행, {len(existing_ids)}개 경기')
    else:
        existing     = pd.DataFrame()
        existing_ids = set()
        print('기존 데이터 없음 → 새로 수집')

    print('경기 목록 수집 중...')
    match_list = get_match_urls(driver)
    print(f'전체 경기: {len(match_list)}개')

    # 미완료 경기도 kbo_games.csv 일정에 추가 (오늘 예측용)
    GAMES_PATH = 'kbo_games.csv'
    upcoming = [m for m in match_list if not m['finished'] and m['home'] and m['away']]
    if upcoming:
        from datetime import datetime as _dt
        today_str = _dt.today().strftime('%Y-%m-%d')
        games_new = []
        if os.path.exists(GAMES_PATH):
            gdf = pd.read_csv(GAMES_PATH)
            existing_game_keys = set(zip(gdf['date'], gdf['home']))
        else:
            gdf = pd.DataFrame()
            existing_game_keys = set()
        for m in upcoming:
            # 날짜 문자열을 YYYY-MM-DD로 변환
            raw_date = m['date']
            if raw_date.startswith('Today'):
                norm_date = today_str
            elif raw_date.startswith('Yesterday'):
                from datetime import timedelta
                norm_date = (_dt.today() - timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                try:
                    norm_date = _dt.strptime(raw_date.split(' - ')[0].strip(), '%d %b %Y').strftime('%Y-%m-%d')
                except:
                    norm_date = raw_date
            if (norm_date, m['home']) not in existing_game_keys:
                games_new.append({
                    'date': norm_date, 'home': m['home'], 'away': m['away'],
                    'slot': m['slot'], 'home_score': None, 'away_score': None,
                    'winner': None, 'winner_is_home': None,
                })
        if games_new:
            new_games_df = pd.DataFrame(games_new)
            combined_games = pd.concat([gdf, new_games_df], ignore_index=True) if len(gdf) > 0 else new_games_df
            combined_games.to_csv(GAMES_PATH, index=False, encoding='utf-8-sig')
            print(f'kbo_games.csv 일정 추가: {len(games_new)}경기')
            for g in games_new:
                print(f"  {g['date']} slot{g['slot']} {g['home']} vs {g['away']}")

    new_matches = []
    for m in match_list:
        if not m['finished']:
            continue
        if m['match_id'] in existing_ids:
            print(f"  스킵: {m['date']} slot{m['slot']} {m['home']} vs {m['away']}")
            continue
        new_matches.append(m)

    print(f'새로 수집할 경기: {len(new_matches)}개')

    for match in new_matches:
        print(f"수집: {match['date']} slot{match['slot']} "
              f"{match['home']} vs {match['away']}")
        rows = []
        for attempt in range(3):
            rows = scrape_match(driver, match['url'],
                                winner_is_home=match['winner_is_home'])
            if rows:
                break
            print(f'  재시도 {attempt+1}...')
            time.sleep(3)

        for row in rows:
            row.update({
                'date':       normalize_date(match['date']),
                'slot':       match['slot'],
                'home':       match['home'],
                'away':       match['away'],
                'winner':     match['home'] if match['winner_is_home'] else match['away'],
                'winner_is_home': match['winner_is_home'],
                'home_score': match['home_score'],
                'away_score': match['away_score'],
            })
        new_rows.extend(rows)
        print(f'  → {len(rows)}개 북메이커 수집')
        time.sleep(2)

except Exception as e:
    print(f'오류: {e}')
    import traceback
    traceback.print_exc()

finally:
    driver.quit()

if new_rows:
    new_df = pd.DataFrame(new_rows)
    # 컬럼 순서 정리
    cols = [
        'match_id','date','slot','home','away',
        'winner','winner_is_home','home_score','away_score',
        'bookmaker',
        'home_open','home_close','home_change','home_direction',
        'away_open','away_close','away_change','away_direction',
        'winner_direction','odds_ratio','consensus'
    ]
    new_df = new_df[[c for c in cols if c in new_df.columns]]

    if len(existing) > 0:
        # 기존 CSV에 새 컬럼 없으면 추가
        for col in new_df.columns:
            if col not in existing.columns:
                existing[col] = None
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    combined.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n완료: {len(new_rows)}행 추가 (총 {len(combined)}행)')
else:
    print('\n새 데이터 없음')