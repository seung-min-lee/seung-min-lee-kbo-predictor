"""
kbo_retry_missing.py
GambleCity/Kobet/Melbet/Cloudbet open 데이터 재수집
전략: 각 경기 페이지에서 신뢰 BM을 먼저 클릭해 팝업 초기화 후 target BM 시도
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kbo_update import get_driver, get_match_urls, normalize_date, scrape_team_odds, EXCLUDE
from collection.bm_utils import recalc_winner_direction
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import pandas as pd
import time

CSV_PATH      = 'kbo_odds.csv'
FILL_FROM     = '2026-04-26'
FILL_TO       = '2026-04-27'
RESTART_EVERY = 4

TARGET_BMS  = {'GambleCity', 'Kobet', 'Melbet', 'Cloudbet'}
NO_POPUP    = {'Momobet', 'Roobet', 'Stake.com', 'VOBET'}
# 팝업 초기화용으로 신뢰할 수 있는 BM (알파벳 순서로 GambleCity보다 앞에 오는 것들)
INIT_BMS    = {'10x10bet', '1xBet', '22Bet', 'Alphabet', 'BetInAsia',
               'Bets.io', 'Betsson', 'bwin', 'Pinnacle', 'bet365', 'Betway'}

df = pd.read_csv(CSV_PATH)

# 재수집 대상 (Apr 26 slot 2,3,4,5 강제 재수집 - 기존 데이터 무시)
target_mask = (
    df['bookmaker'].isin(TARGET_BMS) &
    (df['date'] >= FILL_FROM) &
    (df['date'] < FILL_TO) &
    (df['slot'].isin([2, 3, 4, 5]))
)
target_ids = set(df[target_mask]['match_id'].unique())
print(f'재수집 대상: {len(target_ids)}경기')

driver = get_driver()
updated = 0

try:
    print('경기 URL 목록 수집 중...')
    match_list = get_match_urls(driver, stop_before=FILL_FROM)
    target_matches = [m for m in match_list if m['match_id'] in target_ids and m['finished']]
    print(f'URL 매칭: {len(target_matches)}경기')

    for idx, match in enumerate(target_matches):
        if idx > 0 and idx % RESTART_EVERY == 0:
            print(f'\n  [드라이버 재시작] {idx}/{len(target_matches)}...')
            try: driver.quit()
            except: pass
            driver = get_driver()
            time.sleep(2)

        norm_date = normalize_date(match['date'])
        mid = match['match_id']
        print(f'\n수집: {norm_date} {match["home"]} vs {match["away"]}')

        driver.get(match['url'])
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        except:
            print('  → 로딩 실패')
            continue
        time.sleep(3)

        # 모든 BM 요소 pre-fetch
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        bm_odds = {}  # {bm_name: (home_el, away_el)}
        for nel in name_els:
            name = nel.text.strip()
            if not name or name in EXCLUDE or name in NO_POPUP:
                continue
            try:
                row = nel
                for _ in range(3):
                    row = row.find_element(By.XPATH, '..')
                odds_els = row.find_elements(By.CSS_SELECTOR, 'p.odds-text')
                if len(odds_els) >= 2:
                    bm_odds[name] = (odds_els[0], odds_els[-1])
            except:
                continue

        print(f'  사용 가능 BM: {list(bm_odds.keys())}')

        # 팝업 초기화: INIT_BM 중 첫 번째 것을 클릭 후 ESC
        init_done = False
        for init_bm in sorted(INIT_BMS):
            if init_bm in bm_odds:
                init_el = bm_odds[init_bm][0]  # home_el
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", init_el)
                    driver.execute_script("window.scrollBy(0,-150);")
                    time.sleep(0.5)
                    ActionChains(driver).move_to_element(init_el).click().perform()
                    time.sleep(2.5)
                    # 팝업 확인
                    popup = driver.execute_script(
                        "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');")
                    if popup:
                        print(f'  팝업 초기화 성공 ({init_bm})')
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        time.sleep(1.0)
                        init_done = True
                        break
                    else:
                        print(f'  {init_bm} 클릭 후 팝업 없음')
                except Exception as e:
                    print(f'  초기화 오류 ({init_bm}): {e}')

        if not init_done:
            # 어떤 BM이든 첫 번째 것으로 초기화 시도
            for bm_name, (home_el, _) in bm_odds.items():
                if bm_name in TARGET_BMS:
                    continue
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", home_el)
                    driver.execute_script("window.scrollBy(0,-150);")
                    time.sleep(0.5)
                    ActionChains(driver).move_to_element(home_el).click().perform()
                    time.sleep(2.5)
                    popup = driver.execute_script(
                        "return document.querySelector('div.height-content[class*=\"bg-gray-med_light\"]');")
                    if popup:
                        print(f'  팝업 초기화 성공 ({bm_name}) [fallback]')
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        time.sleep(1.0)
                        init_done = True
                        break
                except:
                    continue

        if not init_done:
            print('  → 팝업 초기화 실패, 스킵')
            continue

        # 이제 target BM 시도
        match_updated = 0
        for bm in sorted(TARGET_BMS):
            if bm not in bm_odds:
                continue
            mask = (df['match_id'] == mid) & (df['bookmaker'] == bm)
            if not mask.any():
                continue
            # 강제 재수집 - 기존 데이터 덮어쓰기

            home_el, away_el = bm_odds[bm]
            try:
                home_data = scrape_team_odds(driver, home_el)
                away_data = scrape_team_odds(driver, away_el)

                if home_data and home_data.get('openVal'):
                    df.loc[mask, 'home_open']      = home_data['openVal']
                    df.loc[mask, 'home_close']     = home_data['closeVal']
                    df.loc[mask, 'home_direction'] = home_data['direction']
                    df.loc[mask, 'home_change']    = home_data['change']
                if away_data and away_data.get('openVal'):
                    df.loc[mask, 'away_open']      = away_data['openVal']
                    df.loc[mask, 'away_close']     = away_data['closeVal']
                    df.loc[mask, 'away_direction'] = away_data['direction']
                    df.loc[mask, 'away_change']    = away_data['change']

                ho = home_data and home_data.get('openVal')
                ao = away_data and away_data.get('openVal')
                print(f'  {bm}: home={ho}  away={ao}')
                if ho or ao:
                    match_updated += 1

            except Exception as e:
                print(f'  {bm} 오류: {e}')
                continue

            time.sleep(0.5)

        print(f'  → {match_updated}개 BM 업데이트')
        updated += match_updated
        time.sleep(1)

except Exception as e:
    print(f'오류: {e}')
    import traceback; traceback.print_exc()

finally:
    try: driver.quit()
    except: pass

if updated > 0:
    df = recalc_winner_direction(df)
    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n완료: {updated}개 업데이트 → {CSV_PATH} 저장')
else:
    print('\n업데이트 없음')
