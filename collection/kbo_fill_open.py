"""
kbo_fill_open.py
4-22 이후 경기에 대해 클릭 팝업으로 open/close/direction 수집 후 CSV 업데이트
- bookmaker 요소를 페이지 로드 시 한 번만 pre-fetch하여 stale element 방지
- headless 모드 사용 (ActionChains 클릭으로 팝업 트리거 확인됨)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kbo_update import get_driver, get_match_urls, normalize_date, scrape_team_odds, EXCLUDE
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time

CSV_PATH      = 'kbo_odds.csv'
FILL_FROM     = '2026-04-22'
RESTART_EVERY = 3

df = pd.read_csv(CSV_PATH)

# open 없는 경기 대상 (Momobet/Roobet/Stake.com/VOBET은 팝업 없음 → 제외)
NO_POPUP_BMS = {'Momobet', 'Roobet', 'Stake.com', 'VOBET'}
target_ids = set(
    df[(df['home_open'].isna()) & (df['date'] >= FILL_FROM)
       & ~df['bookmaker'].isin(NO_POPUP_BMS)]['match_id'].unique()
)
print(f'open 수집 대상: {len(target_ids)}경기')

driver = get_driver()
updated = 0

try:
    print('경기 URL 목록 수집 중...')
    match_list = get_match_urls(driver, stop_before=FILL_FROM)
    target_matches = [m for m in match_list if m['match_id'] in target_ids and m['finished']]
    print(f'URL 매칭 완료: {len(target_matches)}경기')

    for idx, match in enumerate(target_matches):
        if idx > 0 and idx % RESTART_EVERY == 0:
            print(f'\n  [드라이버 재시작] {idx}/{len(target_matches)}경기 완료...')
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

        # bookmaker 요소 한 번에 pre-fetch
        name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
        bm_odds = {}  # {bm_name: (home_el, away_el)}
        for nel in name_els:
            name = nel.text.strip()
            if not name or name in EXCLUDE or name in NO_POPUP_BMS:
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

        match_updated = 0
        for bm, (home_el, away_el) in bm_odds.items():
            mask = (df['match_id'] == mid) & (df['bookmaker'] == bm)
            if not mask.any():
                continue

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

                match_updated += 1
                print(f'  {bm}: home open={home_data and home_data.get("openVal")} '
                      f'close={home_data and home_data.get("closeVal")} '
                      f'dir={home_data and home_data.get("direction")} / '
                      f'away open={away_data and away_data.get("openVal")} '
                      f'close={away_data and away_data.get("closeVal")} '
                      f'dir={away_data and away_data.get("direction")}')

            except Exception as e:
                print(f'  {bm} 오류: {e}')
                continue

        print(f'  → {match_updated}개 북메이커 업데이트')
        updated += match_updated
        time.sleep(1)

except Exception as e:
    print(f'오류: {e}')
    import traceback; traceback.print_exc()

finally:
    try: driver.quit()
    except: pass

if updated > 0:
    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n완료: {updated}개 북메이커 open 데이터 업데이트 → {CSV_PATH} 저장')
else:
    print('\n업데이트 없음')
