"""
오늘 경기 BM별 현재 배당 직접 추출 (팝업 없음, Selenium)
→ kbo_today_odds.json의 bm_close 필드 업데이트

p.odds-text / a.odds-link 에서 직접 읽음 → 안정적
사용: python collect_today_odds_selenium.py
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json, time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime as _dt

TODAY = _dt.today().strftime('%Y-%m-%d')
KBO_URL = 'https://www.oddsportal.com/baseball/south-korea/kbo/'
RESULTS_URL = 'https://www.oddsportal.com/baseball/south-korea/kbo/results/'
TODAY_ODDS_PATH = 'kbo_today_odds.json'
FAKE_BMS = {'My coupon', 'User Predictions', 'Betfair Exchange'}

TEAM_MAP = {
    'Doosan Bears': 'Doosan Bears', 'LG Twins': 'LG Twins',
    'KT Wiz': 'KT Wiz Suwon', 'KT Wiz Suwon': 'KT Wiz Suwon',
    'SSG Landers': 'SSG Landers', 'NC Dinos': 'NC Dinos',
    'Samsung Lions': 'Samsung Lions', 'KIA Tigers': 'KIA Tigers',
    'Lotte Giants': 'Lotte Giants', 'Hanwha Eagles': 'Hanwha Eagles',
    'Kiwoom Heroes': 'Kiwoom Heroes',
}


def make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--host-resolver-rules=MAP contentdeliverynetwork.cc 127.0.0.1, MAP *.contentdeliverynetwork.cc 127.0.0.1')
    opts.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    d = webdriver.Chrome(options=opts)
    d.execute_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return d


def accept_cookies(driver):
    try:
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '#onetrust-accept-btn-handler')))
        driver.execute_script('arguments[0].click();', btn)
        time.sleep(1)
        print('  쿠키 수락')
    except:
        pass


def normalize_date(raw):
    s = str(raw).strip()
    today = _dt.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        from datetime import timedelta
        return (today - timedelta(days=1)).strftime('%Y-%m-%d')
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y', '%Y-%m-%d'):
        try:
            return _dt.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s


MATCH_JS = """
var results = [], seen = {};
var currentDate = '';
var rows = document.querySelectorAll('div.eventRow');
for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var dateEl = row.querySelector('[data-testid="date-header"]');
    if (dateEl && dateEl.innerText.trim()) currentDate = dateEl.innerText.trim();

    var kboLinks = [];
    var allLinks = row.querySelectorAll('a[href*="/kbo/"]');
    for (var j = 0; j < allLinks.length; j++) {
        var tail = allLinks[j].href.split('/kbo/')[1];
        if (tail && tail.length > 5 && tail.indexOf('results') !== 0
            && tail.indexOf('standings') !== 0 && tail.indexOf('?') !== 0) {
            kboLinks.push(allLinks[j]);
        }
    }
    var link = kboLinks.length > 0 ? kboLinks[0] : row.querySelector('a[href*="/h2h/"]');
    if (!link) continue;
    var href = link.href;
    if (seen[href]) continue;
    seen[href] = true;

    var teamEls = row.querySelectorAll('p.participant-name');
    var teams = [];
    for (var k = 0; k < teamEls.length && teams.length < 2; k++) {
        var t = teamEls[k].innerText.trim();
        if (t) teams.push(t);
    }
    if (teams.length < 2) continue;
    results.push({date: currentDate, home: teams[0], away: teams[1], url: href,
                  isH2H: href.indexOf('/h2h/') !== -1});
}
return results;
"""


def h2h_to_kbo_url(h2h_url, home_team, away_team):
    m = re.search(r'#([A-Za-z0-9]+)$', h2h_url)
    if not m:
        return h2h_url
    match_id = m.group(1)
    return (f'https://www.oddsportal.com/baseball/south-korea/kbo/'
            f'{home_team.lower().replace(" ", "-")}-'
            f'{away_team.lower().replace(" ", "-")}-{match_id}/')


def get_today_match_urls(driver):
    today_matches, seen_teams = [], set()

    for page_url in [KBO_URL, RESULTS_URL]:
        if len(today_matches) >= 5:
            break
        driver.get(page_url)
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div.eventRow')))
            time.sleep(3)
        except:
            time.sleep(4)
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(1.5)

        if page_url == KBO_URL:
            accept_cookies(driver)
            time.sleep(1)

        raw = driver.execute_script(MATCH_JS)
        if not raw:
            print(f'  {page_url.split("/")[-2]} → 0개')
            continue

        added = 0
        for m in raw:
            norm = normalize_date(m['date'])
            if norm != TODAY:
                continue
            home = TEAM_MAP.get(m['home'], m['home'])
            away = TEAM_MAP.get(m['away'], m['away'])
            key = (home, away)
            if key in seen_teams:
                continue
            seen_teams.add(key)
            url = m['url']
            if m.get('isH2H') or '/h2h/' in url:
                url = h2h_to_kbo_url(url, home, away)
            today_matches.append({'home': home, 'away': away, 'url': url})
            added += 1

        print(f'  {page_url.split("/")[-2] or "kbo"} → {added}개 (누적 {len(today_matches)}개)')

    return today_matches[:5]


def scrape_bm_current_odds(driver, url):
    """BM별 현재 배당 직접 추출 (팝업 없음)
    반환: {bm: {'home': float, 'away': float}}
    """
    driver.get(url)
    try:
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        time.sleep(2.5)
    except:
        time.sleep(4)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(1)
    driver.execute_script('window.scrollTo(0, 0)')
    time.sleep(0.5)

    result = {}
    name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
    for nel in name_els:
        name = nel.text.strip()
        if not name or name in FAKE_BMS:
            continue
        try:
            row = nel
            for _ in range(3):
                row = row.find_element(By.XPATH, '..')
            odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
            if not odds_els:
                odds_els = row.find_elements(By.CSS_SELECTOR, 'a.odds-link')
            if len(odds_els) < 2:
                continue
            h = float(odds_els[0].text.strip())
            a = float(odds_els[-1].text.strip())
            if h > 1 and a > 1:
                result[name] = {'home': h, 'away': a}
        except:
            continue

    return result


def main():
    print(f'오늘 경기 BM 현재배당 직접수집: {TODAY}')

    try:
        with open(TODAY_ODDS_PATH, encoding='utf-8') as f:
            today_odds = json.load(f)
    except:
        today_odds = {}

    driver = make_driver()

    try:
        print('경기 목록 수집 중...')
        match_list = get_today_match_urls(driver)
        print(f'오늘 경기 {len(match_list)}개: {[(m["home"], m["away"]) for m in match_list]}')

        if not match_list:
            print('오늘 경기 URL 수집 실패')
            return

        for i, m in enumerate(match_list, 1):
            entry_key = next(
                (k for k, v in today_odds.items()
                 if v.get('home') == m['home'] and v.get('away') == m['away']
                 and v.get('date') == TODAY),
                f'{TODAY}|{i}|{m["home"]}|{m["away"]}'
            )
            entry = today_odds.get(entry_key, {
                'date': TODAY, 'slot': float(i),
                'home': m['home'], 'away': m['away'],
            })

            # 이미 수집된 슬롯 스킵
            if len(entry.get('bm_close', {})) >= 10:
                print(f'\n[slot{i}] {m["home"]} vs {m["away"]} → 이미 수집됨 ({len(entry["bm_close"])}BM), 스킵')
                continue

            print(f'\n[slot{i}] {m["home"]} vs {m["away"]}')
            print(f'  URL: {m["url"]}')

            # 슬롯마다 새 Chrome 인스턴스 (크래시 격리)
            slot_driver = make_driver()
            try:
                bm_data = scrape_bm_current_odds(slot_driver, m['url'])
            except Exception as e:
                print(f'  크래시: {e}')
                bm_data = {}
            finally:
                try:
                    slot_driver.quit()
                except:
                    pass

            print(f'  BM {len(bm_data)}개: {list(bm_data.keys())[:5]}...')

            if bm_data:
                entry['bm_close'] = bm_data
                entry['match_url'] = m['url']
                h_avg = round(sum(v['home'] for v in bm_data.values()) / len(bm_data), 3)
                a_avg = round(sum(v['away'] for v in bm_data.values()) / len(bm_data), 3)
                entry['home_odds'] = h_avg
                entry['away_odds'] = a_avg
                if 'bm_open' not in entry:
                    entry['bm_open'] = bm_data
                print(f'  avg H={h_avg} A={a_avg}')
                for bm, v in list(bm_data.items())[:3]:
                    print(f'    {bm}: H={v["home"]} A={v["away"]}')

            today_odds[entry_key] = entry
            with open(TODAY_ODDS_PATH, 'w', encoding='utf-8') as f:
                json.dump(today_odds, f, ensure_ascii=False, indent=2)

    finally:
        try:
            driver.quit()
        except:
            pass

    with open(TODAY_ODDS_PATH, 'w', encoding='utf-8') as f:
        json.dump(today_odds, f, ensure_ascii=False, indent=2)

    print(f'\n=== 저장 완료: {TODAY_ODDS_PATH} ===')
    print('\n=== 오늘 BM 수집 현황 ===')
    for k, v in today_odds.items():
        if v.get('date') != TODAY:
            continue
        bms = v.get('bm_close', {})
        print(f"  slot{int(v.get('slot', 0))} {v['home']} vs {v['away']}: {len(bms)}BM  H={v.get('home_odds')} A={v.get('away_odds')}")


if __name__ == '__main__':
    main()
