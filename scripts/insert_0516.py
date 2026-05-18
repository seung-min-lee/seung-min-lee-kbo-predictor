"""
05-16 open/close odds + 결과 수집 → kbo_odds.csv 삽입
- OddsPortal h2h 페이지에서 결과(winner) 파싱
- kbo_today_odds.json open 사용
- slot1 close = 라이브배당이므로 NaN
- 나머지 슬롯 close = kbo_today_odds.json bm_close 사용
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import time, re, json, numpy as np, pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

DATE = '2026-05-16'

SLOTS = {
    1.0: {'home': 'KT Wiz Suwon',   'away': 'Hanwha Eagles',  'match_id': 'S0DrbHCk',
          'slug': 'hanwha-eagles-4tfKodg8/kt-wiz-suwon-444SNVEe'},
    2.0: {'home': 'Doosan Bears',    'away': 'Lotte Giants',   'match_id': 'Aonqhgqt',
          'slug': 'doosan-bears-0j2eUlMC/lotte-giants-EXCPojim'},
    3.0: {'home': 'Samsung Lions',   'away': 'KIA Tigers',     'match_id': 'z3Y35aKF',
          'slug': 'kia-tigers-rXhOpG8E/samsung-lions-O6nTMCG7'},
    4.0: {'home': 'NC Dinos',        'away': 'Kiwoom Heroes',  'match_id': 'rTyC3wkS',
          'slug': 'kiwoom-heroes-xjpHPEWl/nc-dinos-O6x8hD4U'},
    5.0: {'home': 'SSG Landers',     'away': 'LG Twins',       'match_id': 'Uk337Lk3',
          'slug': 'lg-twins-jglLOYoe/ssg-landers-fRfCQfHr'},
}

BASE = 'https://www.oddsportal.com/baseball/h2h/'


def make_driver(headless=False):
    opts = Options()
    if headless:
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


def get_winner_from_page(driver, home, away, slug, match_id):
    """OddsPortal h2h 페이지에서 최종 결과 파싱"""
    url = f"{BASE}{slug}/#{match_id}"
    try:
        driver.get(url)
        time.sleep(6)
        body = driver.execute_script("return document.body.innerText;")

        # 패턴: "Team1 X - Y Team2" or "X:Y" with team names nearby
        lines = [l.strip() for l in body.split('\n') if l.strip()]

        home_short = home.split()[0]  # e.g. "KT", "Doosan", "Samsung"
        away_short = away.split()[0]  # e.g. "Hanwha", "Lotte", "KIA"

        for i, line in enumerate(lines):
            if re.search(r'\b\d+\s*[:\-]\s*\d+\b', line):
                context = ' '.join(lines[max(0,i-3):i+4])
                print(f"  점수 컨텍스트: {context[:150]}")
                break

        # OddsPortal 제목에서 score 찾기
        try:
            title = driver.title
            print(f"  페이지 타이틀: {title}")
            m = re.search(r'(\d+)[:\-](\d+)', title)
            if m:
                s1, s2 = int(m.group(1)), int(m.group(2))
                # 타이틀 팀 순서 = URL 슬러그 순서 (첫 번째 팀 slug가 1열)
                slug_home = slug.split('/')[0].split('-')[0].capitalize()  # 첫 번째 팀
                # URL 첫 팀이 점수 왼쪽
                url_first_wins = s1 > s2
                # URL 첫 팀이 실제 home인지 확인
                url_first_is_home = slug_home.lower() in home.lower()
                print(f"  URL 첫팀={slug_home} | url_first_wins={url_first_wins} | url_first_is_home={url_first_is_home}")
                if url_first_wins:
                    winner_is_home = url_first_is_home
                else:
                    winner_is_home = not url_first_is_home
                winner_team = home if winner_is_home else away
                return winner_team, winner_is_home
        except:
            pass

        # og:title 메타태그 시도
        try:
            og = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:title"]')
            content = og.get_attribute('content')
            print(f"  og:title: {content}")
            m = re.search(r'(\d+)[:\-](\d+)', content)
            if m:
                s1, s2 = int(m.group(1)), int(m.group(2))
                url_first_is_home = slug.split('/')[0].split('-')[0].lower() in home.lower()
                url_first_wins = s1 > s2
                winner_is_home = url_first_is_home if url_first_wins else not url_first_is_home
                winner_team = home if winner_is_home else away
                return winner_team, winner_is_home
        except:
            pass

    except Exception as e:
        print(f"  오류: {e}")

    return None, None


def calc_dir(ho, hc, ao, ac, wih):
    if any(v is None or (isinstance(v, float) and np.isnan(float(v))) for v in [ho, hc, ao, ac]):
        return np.nan
    if wih is None or (isinstance(wih, float) and np.isnan(float(wih))):
        return np.nan
    hchg = float(hc) - float(ho)
    achg = float(ac) - float(ao)
    wchg = hchg if wih else achg
    lchg = achg if wih else hchg
    if abs(wchg - lchg) < 0.001:
        return np.nan
    return 1.0 if wchg > lchg else 0.0


# ── 기존 결과 확인 ───────────────────────────────────────────────────
games = pd.read_csv('kbo_games.csv')
results = {}

for slot, info in SLOTS.items():
    # slot 포함 검색
    mask = (games['date'] == DATE) & (games['home'] == info['home'])
    row = games[mask]
    if not row.empty:
        r = row.iloc[0]
        if pd.notna(r.get('winner')) and str(r.get('winner')).strip() not in ('', 'nan', 'Postp'):
            wih = bool(r['winner'] == info['home'])
            results[slot] = (r['winner'], wih, int(r['slot']) if pd.notna(r.get('slot')) else slot)
            print(f"slot{int(slot)}: {info['home']} vs {info['away']} → {r['winner']} (wih={wih})")
        else:
            results[slot] = (None, None, slot)
    else:
        results[slot] = (None, None, slot)

missing = [s for s, r in results.items() if r[0] is None]
print(f"\n결과 없는 슬롯: {[int(s) for s in missing]}")

# ── Selenium으로 결과 수집 ───────────────────────────────────────────
if missing:
    driver = make_driver(headless=True)
    try:
        for slot in missing:
            info = SLOTS[slot]
            print(f"\n[slot{int(slot)}] {info['home']} vs {info['away']}")
            winner, wih = get_winner_from_page(
                driver, info['home'], info['away'], info['slug'], info['match_id']
            )
            if winner is not None:
                results[slot] = (winner, wih, slot)
                print(f"  → 결과: {winner} (wih={wih})")
            else:
                print(f"  → 결과 파싱 실패")
    finally:
        driver.quit()

print()
print("=== 수집된 결과 ===")
for slot in sorted(results):
    r = results[slot]
    print(f"  slot{int(slot)}: winner={r[0]} wih={r[1]}")

# ── kbo_today_odds.json 로드 ─────────────────────────────────────────
with open('kbo_today_odds.json', encoding='utf-8') as f:
    today_json = json.load(f)

# ── kbo_odds.csv 구성 ────────────────────────────────────────────────
odds_df = pd.read_csv('kbo_odds.csv')

# 이미 05-16 데이터 있으면 삭제
existing = odds_df[odds_df['date'] == DATE]
if not existing.empty:
    print(f"\n기존 05-16 데이터 {len(existing)}행 제거")
    odds_df = odds_df[odds_df['date'] != DATE]

new_rows = []

for slot, info in sorted(SLOTS.items()):
    key = f"{DATE}|{int(slot)}|{info['home']}|{info['away']}"
    if key not in today_json:
        print(f"slot{int(slot)}: JSON 키 없음 → 스킵")
        continue

    sd = today_json[key]
    bm_open = sd.get('bm_open', {})
    bm_close = sd.get('bm_close', {})

    winner, wih, _ = results.get(slot, (None, None, slot))
    winner_val = winner if winner else float('nan')
    wih_val = wih if wih is not None else float('nan')

    # slot1 close 무효 (라이브배당) → None
    use_close = (slot != 1.0)

    all_bms = set(bm_open.keys()) | (set(bm_close.keys()) if use_close else set())

    for bm in sorted(all_bms):
        bo = bm_open.get(bm, {})
        bc = bm_close.get(bm, {}) if use_close else {}

        ho = bo.get('home')
        ao = bo.get('away')
        hc = bc.get('home') if bc else None
        ac = bc.get('away') if bc else None

        if ho is None and hc is None:
            continue

        hchg = round(float(hc) - float(ho), 3) if (ho and hc) else float('nan')
        achg = round(float(ac) - float(ao), 3) if (ao and ac) else float('nan')
        wd = calc_dir(ho, hc, ao, ac, wih)

        new_rows.append({
            'date':           DATE,
            'slot':           slot,
            'home':           info['home'],
            'away':           info['away'],
            'match_id':       info['match_id'],
            'bookmaker':      bm,
            'home_open':      float(ho) if ho else float('nan'),
            'home_close':     float(hc) if hc else float('nan'),
            'away_open':      float(ao) if ao else float('nan'),
            'away_close':     float(ac) if ac else float('nan'),
            'home_change':    hchg,
            'away_change':    achg,
            'winner':         winner_val,
            'winner_is_home': wih_val,
            'winner_direction': wd,
        })

new_df = pd.DataFrame(new_rows)
print(f"\n새 행: {len(new_df)}개")

# 컬럼 순서 맞추기
for col in odds_df.columns:
    if col not in new_df.columns:
        new_df[col] = float('nan')
new_df = new_df[odds_df.columns]

final_df = pd.concat([odds_df, new_df], ignore_index=True)
final_df.to_csv('kbo_odds.csv', index=False)
print(f"kbo_odds.csv 저장 완료: {len(final_df)}행")

# 요약 출력
print()
print("=== 삽입 요약 ===")
for slot in sorted(SLOTS):
    info = SLOTS[slot]
    mask = (new_df['slot'] == slot)
    s = new_df[mask]
    bm_count = len(s)
    has_close = s['home_close'].notna().sum()
    wd_count = s['winner_direction'].notna().sum()
    print(f"  slot{int(slot)} {info['home']} vs {info['away']}: {bm_count}BM, close={has_close}, wd={wd_count}")
