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
        from selenium.webdriver.chrome.service import Service
        import glob as _glob, os as _os
        _cached = _glob.glob(_os.path.join(_os.path.expanduser('~'), '.wdm', 'drivers',
                             'chromedriver', '**', 'chromedriver.exe'), recursive=True)
        if _cached:
            _driver_path = sorted(_cached)[-1]
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            _driver_path = ChromeDriverManager().install()
        driver = webdriver.Chrome(service=Service(_driver_path), options=options)

    driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

SCRAPE_FROM = '2026-03-28'  # 정규시즌 시작일

JS_EXTRACT = """
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
"""

def get_match_urls(driver, stop_before=None):
    """여러 페이지에서 경기 목록 수집. stop_before 날짜 이전 데이터가 나오면 중단.
    페이지네이션 버튼(a[data-number])은 페이지 하단 스크롤 후 DOM에 나타남.
    """
    all_matches = []
    seen_ids = set()

    # 첫 페이지 로드
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    time.sleep(3)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
    except:
        print('  결과 페이지 로딩 실패')
        return []
    time.sleep(2)

    for page in range(1, 20):
        # 하단 스크롤 → 페이지네이션 버튼 렌더링 유도
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        time.sleep(2)

        print(f'  결과 페이지 {page} 수집 중...')
        page_matches = driver.execute_script(JS_EXTRACT)
        if not page_matches:
            print(f'  페이지 {page} 데이터 없음 → 중단')
            break

        added = 0
        reached_stop = False
        for m in page_matches:
            if m['match_id'] in seen_ids:
                continue
            seen_ids.add(m['match_id'])
            norm = normalize_date(m['date'])
            # 정상 파싱된 날짜(YYYY-MM-DD 형식)에 대해서만 stop 체크
            if stop_before and len(norm) == 10 and norm < stop_before:
                reached_stop = True
                continue
            all_matches.append(m)
            added += 1

        print(f'    → {added}개 경기 추가 (누적 {len(all_matches)}개)')

        if reached_stop:
            print(f'  {stop_before} 이전 날짜 도달 → 수집 완료')
            break

        # 다음 페이지 버튼 (스크롤 후 visible)
        next_btn = driver.execute_script("""
            const cur = document.querySelector('a[data-number].active');
            if (!cur) return null;
            const curNum = parseInt(cur.getAttribute('data-number'));
            const btns = [...document.querySelectorAll('a[data-number]')];
            return btns.find(b => parseInt(b.getAttribute('data-number')) === curNum + 1) || null;
        """)

        if not next_btn:
            print('  다음 페이지 버튼 없음 → 수집 완료')
            break

        try:
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(3)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
            time.sleep(2)
        except Exception as e:
            print(f'  페이지 이동 실패: {e}')
            break

    # 날짜별 slot 재계산 (KBO 최대 5경기)
    date_counter = {}
    valid_matches = []
    for m in all_matches:
        d = normalize_date(m['date'])
        date_counter[d] = date_counter.get(d, 0) + 1
        if date_counter[d] > 5:
            print(f'  경고: {d} slot{date_counter[d]} 초과 스킵 ({m["home"]} vs {m["away"]})')
            continue
        m['slot'] = date_counter[d]
        valid_matches.append(m)
    return valid_matches

def scrape_team_odds(driver, odds_el):
    """특정 팀 배당 클릭 후 open/close/direction/change 수집"""
    from selenium.webdriver.common.action_chains import ActionChains
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

        // Opening odds: in the mt-2 section
        const openSection = popup.querySelector('div[class*="mt-2"]');
        if (openSection) {
            const boldEls = openSection.querySelectorAll('.font-bold');
            for (const b of boldEls) {
                const v = parseFloat(b.innerText);
                if (!isNaN(v) && v > 1) { openVal = v; break; }
            }
        }

        // Closing odds: second column in the flex-row (first numeric bold not red/green)
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

        // Direction and change
        const redEl = popup.querySelector('[class*="text-red-dark"]');
        const greenEl = popup.querySelector('[class*="text-green-dark"]');
        if (redEl) { direction = 0; change = redEl.innerText.trim(); }
        else if (greenEl) { direction = 1; change = greenEl.innerText.trim(); }
        else if (openVal && closeVal && openVal !== closeVal) {
            direction = closeVal > openVal ? 1 : 0;
            change = (closeVal - openVal).toFixed(2);
        }

        return {openVal, closeVal, direction, change};
    """)

    # 패널 닫기
    try:
        driver.execute_script("arguments[0].click();", odds_el)
        for _ in range(5):
            if not driver.execute_script(
                "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');"):
                break
            time.sleep(0.3)
    except:
        pass

    return data

def get_odds_direction(driver, el):
    """odds 셀을 클릭하여 팝업에서 방향 감지 (scrape_team_odds 경량화).
    1 = 배당↑(green), 0 = 배당↓(red), None = 감지 실패
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", el)
        driver.execute_script("window.scrollBy(0,-100);")
        driver.execute_script("arguments[0].click();", el)
        time.sleep(1.5)
    except Exception:
        return None

    direction = driver.execute_script("""
        const panels = document.querySelectorAll('.bg-gray-light');
        for (const panel of panels) {
            const h1 = panel.querySelector('h1');
            if (!h1) continue;
            const ce = panel.querySelector('.text-green-dark,.text-red-dark');
            if (ce) return ce.classList.contains('text-green-dark') ? 1 : 0;
            // open→close 계산으로 방향 추정
            const nums = [...panel.querySelectorAll('.font-bold')]
                .map(e => parseFloat(e.innerText)).filter(v => !isNaN(v) && v > 1);
            if (nums.length >= 2 && nums[0] !== nums[1]) return nums[1] > nums[0] ? 1 : 0;
        }
        return null;
    """)

    # 팝업 닫기
    try:
        driver.execute_script("arguments[0].click();", el)
        for _ in range(4):
            if driver.execute_script(
                    "return document.querySelectorAll('.bg-gray-light').length;") <= 2:
                break
            time.sleep(0.2)
    except Exception:
        pass

    return direction

def scrape_match(driver, url, winner_is_home=True):
    """한 경기의 모든 북메이커 closing 배당 + 방향 수집
    Pass 1: closing 배당 텍스트 수집 (클릭 없음, 빠름)
    Pass 2: 배당 방향 수집 (클릭 기반, bookmaker별 element 재탐색)
    """
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    except:
        print('  → 로딩 실패')
        return []
    time.sleep(3)

    # ── Pass 1: closing 배당 수집 ─────────────────────────────
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    results = []
    bm_order = []   # 순서 보존용

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
        consensus  = 'home' if home_close < away_close else 'away'

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
        bm_order.append(name)

    if not results:
        return results

    # ── Pass 2: 방향 수집 (element 재탐색으로 stale 방지) ──────
    for i, bm in enumerate(bm_order):
        try:
            current_name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
            target_nel = None
            for nel in current_name_els:
                if nel.text.strip() == bm:
                    target_nel = nel
                    break
            if target_nel is None:
                continue

            row = target_nel
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if len(odds_els) < 2:
                continue

            home_dir = get_odds_direction(driver, odds_els[0])
            away_dir = get_odds_direction(driver, odds_els[-1])

            results[i]['home_direction']   = home_dir
            results[i]['away_direction']   = away_dir
            results[i]['winner_direction'] = home_dir if winner_is_home else away_dir

        except Exception as e:
            print(f'    direction 수집 실패 ({bm}): {e}')
            continue

    return results

# ── 메인 ──────────────────────────────────────────────
RESTART_EVERY = 5   # N경기마다 드라이버 재시작 (Chrome 메모리 누수 방지)

driver   = get_driver()
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
    match_list = get_match_urls(driver, stop_before=SCRAPE_FROM)
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

    # kbo_games.csv 에서 사전 slot 조회 (결과 페이지 순서 대신 경기 시작 순서 사용)
    pregame_slot = {}
    if os.path.exists(GAMES_PATH):
        _gdf = pd.read_csv(GAMES_PATH)
        for _, _g in _gdf.iterrows():
            key = (str(_g['date']).strip(), str(_g['home']).strip(), str(_g['away']).strip())
            if not pd.isna(_g['slot']):
                pregame_slot[key] = int(_g['slot'])

    today_str_main = _dt.today().strftime('%Y-%m-%d')
    new_matches = []
    for m in match_list:
        if not m['finished']:
            continue
        norm_date_check = normalize_date(m['date'])
        if norm_date_check >= today_str_main:
            print(f"  오늘 경기 스킵(예측 대상): {norm_date_check} {m['home']} vs {m['away']}")
            continue
        if m['match_id'] in existing_ids:
            print(f"  스킵: {m['date']} slot{m['slot']} {m['home']} vs {m['away']}")
            continue
        new_matches.append(m)

    print(f'새로 수집할 경기: {len(new_matches)}개')

    for idx, match in enumerate(new_matches):
        # N경기마다 드라이버 재시작 (Chrome 메모리 누수 방지)
        if idx > 0 and idx % RESTART_EVERY == 0:
            print(f'\n  [드라이버 재시작] {idx}/{len(new_matches)}경기 완료...')
            try:
                driver.quit()
            except Exception:
                pass
            driver = get_driver()
            time.sleep(2)

        norm_date = normalize_date(match['date'])
        slot = pregame_slot.get((norm_date, match['home'], match['away']), match['slot'])
        if slot != match['slot']:
            print(f"수집: {norm_date} slot{slot}(사전)←결과페이지slot{match['slot']} "
                  f"{match['home']} vs {match['away']}")
        else:
            print(f"수집: {norm_date} slot{slot} {match['home']} vs {match['away']}")

        rows = []
        for attempt in range(3):
            try:
                rows = scrape_match(driver, match['url'],
                                    winner_is_home=match['winner_is_home'])
            except Exception as e:
                err = str(e).lower()
                if 'invalid session id' in err or 'no such session' in err:
                    print(f'  세션 오류 → 드라이버 재시작 후 재시도')
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = get_driver()
                    time.sleep(2)
                    continue
                print(f'  오류 (attempt {attempt+1}): {e}')
            if rows:
                break
            print(f'  재시도 {attempt+1}...')
            time.sleep(3)

        for row in rows:
            row.update({
                'date':           norm_date,
                'slot':           slot,
                'home':           match['home'],
                'away':           match['away'],
                'winner':         match['home'] if match['winner_is_home'] else match['away'],
                'winner_is_home': match['winner_is_home'],
                'home_score':     match['home_score'],
                'away_score':     match['away_score'],
            })
        new_rows.extend(rows)
        dir_count = sum(1 for r in rows if r.get('home_direction') is not None)
        print(f'  → {len(rows)}개 북메이커 수집 (방향 데이터: {dir_count}개)')
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