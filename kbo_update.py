from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time, os, tempfile
from datetime import datetime as _dt, timedelta as _td

def _atomic_csv(path, df):
    dir_ = os.path.dirname(os.path.abspath(path)) or '.'
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as f:
            df.to_csv(f, index=False)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise

def normalize_date(raw):
    """'Today, 25 Apr' / 'Yesterday, 24 Apr' / '21 Apr 2026' ??'YYYY-MM-DD'"""
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

SCRAPE_FROM = '2026-03-28'  # ?뺢퇋?쒖쫵 ?쒖옉??

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
        // Postp(?곌린) 媛먯?: score ?먮━??'Postp.' ?띿뒪???щ? ?뺤씤
        const allText=row.innerText||'';
        const isPostp=!(!isNaN(homeScore)&&!isNaN(awayScore))&&/postp/i.test(allText);
        results.push({
            date:currentDate, url:href,
            match_id:href.split('#')[1],
            home:teams[0]||'', away:teams[1]||'',
            home_score:isPostp?null:(homeScore||0),
            away_score:isPostp?null:(awayScore||0),
            winner_is_home:isPostp?null:(homeScore>awayScore),
            finished:!isNaN(homeScore)&&!isNaN(awayScore)&&homeScore!==awayScore,
            postp:isPostp
        });
    });
    return results;
"""

def get_match_urls(driver, stop_before=None):
    """?щ윭 ?섏씠吏?먯꽌 寃쎄린 紐⑸줉 ?섏쭛. stop_before ?좎쭨 ?댁쟾 ?곗씠?곌? ?섏삤硫?以묐떒.
    ?섏씠吏?ㅼ씠??踰꾪듉(a[data-number])? ?섏씠吏 ?섎떒 ?ㅽ겕濡???DOM???섑???
    """
    all_matches = []
    seen_ids = set()

    # 泥??섏씠吏 濡쒕뱶
    driver.get('https://www.oddsportal.com/baseball/south-korea/kbo/results/')
    time.sleep(3)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
    except:
        print('  寃곌낵 ?섏씠吏 濡쒕뵫 ?ㅽ뙣')
        return []
    time.sleep(2)

    for page in range(1, 20):
        # ?섎떒 ?ㅽ겕濡????섏씠吏?ㅼ씠??踰꾪듉 ?뚮뜑留??좊룄
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        time.sleep(2)

        print(f'  寃곌낵 ?섏씠吏 {page} ?섏쭛 以?..')
        page_matches = driver.execute_script(JS_EXTRACT)
        if not page_matches:
            print(f'  ?섏씠吏 {page} ?곗씠???놁쓬 ??以묐떒')
            break

        added = 0
        reached_stop = False
        for m in page_matches:
            if m['match_id'] in seen_ids:
                continue
            seen_ids.add(m['match_id'])
            norm = normalize_date(m['date'])
            # ?뺤긽 ?뚯떛???좎쭨(YYYY-MM-DD ?뺤떇)????댁꽌留?stop 泥댄겕
            if stop_before and len(norm) == 10 and norm < stop_before:
                reached_stop = True
                continue
            all_matches.append(m)
            added += 1

        print(f'    ??{added}媛?寃쎄린 異붽? (?꾩쟻 {len(all_matches)}媛?')

        if reached_stop:
            print(f'  {stop_before} ?댁쟾 ?좎쭨 ?꾨떖 ???섏쭛 ?꾨즺')
            break

        # ?ㅼ쓬 ?섏씠吏 踰꾪듉 (?ㅽ겕濡???visible)
        next_btn = driver.execute_script("""
            const cur = document.querySelector('a[data-number].active');
            if (!cur) return null;
            const curNum = parseInt(cur.getAttribute('data-number'));
            const btns = [...document.querySelectorAll('a[data-number]')];
            return btns.find(b => parseInt(b.getAttribute('data-number')) === curNum + 1) || null;
        """)

        if not next_btn:
            print('  ?ㅼ쓬 ?섏씠吏 踰꾪듉 ?놁쓬 ???섏쭛 ?꾨즺')
            break

        try:
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(3)
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
            time.sleep(2)
        except Exception as e:
            print(f'  ?섏씠吏 ?대룞 ?ㅽ뙣: {e}')
            break

    # ?좎쭨蹂?slot ?ш퀎??(KBO 理쒕? 5寃쎄린)
    date_counter = {}
    valid_matches = []
    for m in all_matches:
        d = normalize_date(m['date'])
        date_counter[d] = date_counter.get(d, 0) + 1
        if date_counter[d] > 5:
            print(f'  寃쎄퀬: {d} slot{date_counter[d]} 珥덇낵 ?ㅽ궢 ({m["home"]} vs {m["away"]})')
            continue
        m['slot'] = date_counter[d]
        valid_matches.append(m)
    return valid_matches

def scrape_team_odds(driver, odds_el):
    """?뱀젙 ? 諛곕떦 ?대┃ ??open/close/direction/change ?섏쭛"""
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

        // Direction and change (numeric only)
        if (openVal && closeVal && openVal !== closeVal) {
            direction = closeVal > openVal ? 1 : 0;
            change = (closeVal - openVal).toFixed(2);
        }

        return {openVal, closeVal, direction, change};
    """)

    # ?⑤꼸 ?リ린 (body ?대┃?쇰줈 ?レ쓬 - 媛숈? element ?ы겢由????앹뾽 ?ъ뿴由?諛⑹?)
    try:
        from selenium.webdriver.common.keys import Keys
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        for _ in range(5):
            if not driver.execute_script(
                "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');"):
                break
            time.sleep(0.3)
    except:
        pass

    return data

def get_odds_direction(driver, el):
    """odds ????대┃?섏뿬 ?앹뾽?먯꽌 諛⑺뼢 媛먯? (scrape_team_odds 寃쎈웾??.
    1 = 諛곕떦??green), 0 = 諛곕떦??red), None = 媛먯? ?ㅽ뙣
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", el)
        driver.execute_script("window.scrollBy(0,-100);")
        driver.execute_script("arguments[0].click();", el)
        time.sleep(1.5)
    except Exception:
        return None

    direction = driver.execute_script("""
        // ?앹뾽: class??'fixed'媛 ?ы븿??height-content ?붿냼
        const popup = document.querySelector('div[class*="fixed"][class*="height-content"]');
        if (!popup) return null;
        const text = popup.innerText || '';
        // Opening odds 媛?異붿텧
        const openMatch = text.match(/Opening odds:[\\s\\S]*?([\\d.]{3,})/);
        // Odds movement(closing) 媛?異붿텧
        const closeMatch = text.match(/Odds movement:[\\s\\S]*?([\\d.]{3,})/);
        if (!openMatch || !closeMatch) return null;
        const open = parseFloat(openMatch[1]);
        const close = parseFloat(closeMatch[1]);
        if (isNaN(open) || isNaN(close) || open === close) return null;
        return close > open ? 1 : 0;
    """)

    # ?앹뾽 ?リ린
    try:
        driver.execute_script("arguments[0].click();", el)
        for _ in range(4):
            if not driver.execute_script(
                    "return document.querySelector('div[class*=\"fixed\"][class*=\"height-content\"]');"):
                break
            time.sleep(0.2)
    except Exception:
        pass

    return direction

def scrape_match(driver, url, winner_is_home=True):
    """??寃쎄린??紐⑤뱺 遺곷찓?댁빱 closing 諛곕떦 + 諛⑺뼢 ?섏쭛
    Pass 1: closing 諛곕떦 ?띿뒪???섏쭛 (?대┃ ?놁쓬, 鍮좊쫫)
    Pass 2: 諛곕떦 諛⑺뼢 ?섏쭛 (?대┃ 湲곕컲, bookmaker蹂?element ?ы깘??
    """
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
    except:
        print('  ??濡쒕뵫 ?ㅽ뙣')
        return []
    time.sleep(3)

    # ?? Pass 1: closing 諛곕떦 ?섏쭛 ?????????????????????????????
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    results = []
    bm_order = []   # ?쒖꽌 蹂댁〈??

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

    # ?? Pass 2: 諛⑺뼢 ?섏쭛 (element ?ы깘?됱쑝濡?stale 諛⑹?) ??????
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
            # N議곌굔: ?묒そ direction ?숈씪 ??winner_direction NaN
            if home_dir is not None and away_dir is not None and home_dir == away_dir:
                results[i]['winner_direction'] = None
            else:
                results[i]['winner_direction'] = home_dir if winner_is_home else away_dir

        except Exception as e:
            print(f'    direction ?섏쭛 ?ㅽ뙣 ({bm}): {e}')
            continue

    return results

# ?? 硫붿씤 ??????????????????????????????????????????????
RESTART_EVERY = 5   # N寃쎄린留덈떎 ?쒕씪?대쾭 ?ъ떆??(Chrome 硫붾え由??꾩닔 諛⑹?)

driver   = get_driver()
new_rows = []

try:
    if os.path.exists(CSV_PATH):
        existing    = pd.read_csv(CSV_PATH)
        existing_ids = set(existing['match_id'].unique())
        print(f'湲곗〈 ?곗씠?? {len(existing)}?? {len(existing_ids)}媛?寃쎄린')
    else:
        existing     = pd.DataFrame()
        existing_ids = set()
        print('湲곗〈 ?곗씠???놁쓬 ???덈줈 ?섏쭛')

    print('寃쎄린 紐⑸줉 ?섏쭛 以?..')
    match_list = get_match_urls(driver, stop_before=SCRAPE_FROM)
    print(f'?꾩껜 寃쎄린: {len(match_list)}媛?)

    # 誘몄셿猷?寃쎄린??kbo_games.csv ?쇱젙??異붽? (?ㅻ뒛 ?덉륫??
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
            # ?좎쭨 臾몄옄?댁쓣 YYYY-MM-DD濡?蹂??
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
            _atomic_csv(GAMES_PATH, combined_games)
            print(f'kbo_games.csv ?쇱젙 異붽?: {len(games_new)}寃쎄린')
            for g in games_new:
                print(f"  {g['date']} slot{g['slot']} {g['home']} vs {g['away']}")

    # kbo_games.csv ?먯꽌 ?ъ쟾 slot 議고쉶 (寃곌낵 ?섏씠吏 ?쒖꽌 ???寃쎄린 ?쒖옉 ?쒖꽌 ?ъ슜)
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
        if norm_date_check > today_str_main:
            print(f"  誘몃옒 寃쎄린 ?ㅽ궢(?덉륫 ???: {norm_date_check} {m['home']} vs {m['away']}")
            continue
        if m['match_id'] in existing_ids:
            print(f"  ?ㅽ궢: {m['date']} slot{m['slot']} {m['home']} vs {m['away']}")
            continue
        new_matches.append(m)

    print(f'?덈줈 ?섏쭛??寃쎄린: {len(new_matches)}媛?)

    for idx, match in enumerate(new_matches):
        # N寃쎄린留덈떎 ?쒕씪?대쾭 ?ъ떆??(Chrome 硫붾え由??꾩닔 諛⑹?)
        if idx > 0 and idx % RESTART_EVERY == 0:
            print(f'\n  [?쒕씪?대쾭 ?ъ떆?? {idx}/{len(new_matches)}寃쎄린 ?꾨즺...')
            try:
                driver.quit()
            except Exception:
                pass
            driver = get_driver()
            time.sleep(2)

        norm_date = normalize_date(match['date'])
        slot = pregame_slot.get((norm_date, match['home'], match['away']), match['slot'])
        if slot != match['slot']:
            print(f"?섏쭛: {norm_date} slot{slot}(?ъ쟾)?먭껐怨쇳럹?댁?slot{match['slot']} "
                  f"{match['home']} vs {match['away']}")
        else:
            print(f"?섏쭛: {norm_date} slot{slot} {match['home']} vs {match['away']}")

        rows = []
        for attempt in range(3):
            try:
                rows = scrape_match(driver, match['url'],
                                    winner_is_home=match['winner_is_home'])
            except Exception as e:
                err = str(e).lower()
                if 'invalid session id' in err or 'no such session' in err:
                    print(f'  ?몄뀡 ?ㅻ쪟 ???쒕씪?대쾭 ?ъ떆?????ъ떆??)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = get_driver()
                    time.sleep(2)
                    continue
                print(f'  ?ㅻ쪟 (attempt {attempt+1}): {e}')
            if rows:
                break
            print(f'  ?ъ떆??{attempt+1}...')
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
        print(f'  ??{len(rows)}媛?遺곷찓?댁빱 ?섏쭛 (諛⑺뼢 ?곗씠?? {dir_count}媛?')
        time.sleep(2)

except Exception as e:
    print(f'?ㅻ쪟: {e}')
    import traceback
    traceback.print_exc()

finally:
    driver.quit()

if new_rows:
    new_df = pd.DataFrame(new_rows)
    # 而щ읆 ?쒖꽌 ?뺣━
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
        # 湲곗〈 CSV????而щ읆 ?놁쑝硫?異붽?
        for col in new_df.columns:
            if col not in existing.columns:
                existing[col] = None
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    _atomic_csv(CSV_PATH, combined)
    print(f'\n?꾨즺: {len(new_rows)}??異붽? (珥?{len(combined)}??')
else:
    print('\n???곗씠???놁쓬')