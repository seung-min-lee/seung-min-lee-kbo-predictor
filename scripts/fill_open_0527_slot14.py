"""
05-27 slot1(Doosan vs KT), slot4(Lotte vs LG) 개장배당 재시도
대기시간 증가 및 재시도 로직 추가
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collection.bm_utils import recalc_winner_direction
from kbo_update import get_driver, get_match_urls, normalize_date, scrape_team_odds, EXCLUDE
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time

CSV_PATH = 'kbo_odds.csv'
TARGET_DATE = '2026-05-27'
TARGET_SLOTS = {1.0, 4.0}
NO_POPUP_BMS = {'Momobet', 'Roobet', 'Stake.com', 'VOBET'}

df = pd.read_csv(CSV_PATH)

target_ids = set(
    df[(df['date'] == TARGET_DATE) & (df['slot'].isin(TARGET_SLOTS))
       & (df['home_open'].isna()) & ~df['bookmaker'].isin(NO_POPUP_BMS)]['match_id'].unique()
)
print(f'대상 match_id: {target_ids}')

driver = get_driver()
updated = 0

try:
    print('경기 URL 수집 중...')
    match_list = get_match_urls(driver, stop_before='2026-04-22')
    target_matches = [m for m in match_list if m['match_id'] in target_ids and m['finished']]
    print(f'URL 매칭: {len(target_matches)}경기')

    for match in target_matches:
        norm_date = normalize_date(match['date'])
        mid = match['match_id']
        print(f'\n수집: {norm_date} {match["home"]} vs {match["away"]}')

        for attempt in range(3):
            driver.get(match['url'])
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
            except:
                print(f'  → 로딩 실패 (시도 {attempt+1})')
                time.sleep(3)
                continue
            time.sleep(5)  # 대기시간 증가

            name_els = driver.find_elements(By.CSS_SELECTOR, 'p.height-content.pl-4')
            bm_odds = {}
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

            if bm_odds:
                break
            print(f'  BM 요소 없음, 재시도 {attempt+1}...')
            time.sleep(3)

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
                print(f'  {bm}: home open={home_data and home_data.get("openVal")} / away open={away_data and away_data.get("openVal")}')
            except Exception as e:
                print(f'  {bm} 오류: {e}')
        print(f'  → {match_updated}개 BM 업데이트')
        updated += match_updated
        time.sleep(2)

except Exception as e:
    print(f'오류: {e}')
    import traceback; traceback.print_exc()
finally:
    driver.quit()

if updated > 0:
    df = recalc_winner_direction(df)
    df.to_csv(CSV_PATH, index=False)
    print(f'\n완료: {updated}개 BM 업데이트, kbo_odds.csv 저장')
else:
    print('\n새 데이터 없음 (OddsPortal에 개장배당 없을 수 있음)')
