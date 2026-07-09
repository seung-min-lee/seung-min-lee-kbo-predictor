"""
kbo_fill_open.py
4-22 ?댄썑 寃쎄린??????대┃ ?앹뾽?쇰줈 open/close/direction ?섏쭛 ??CSV ?낅뜲?댄듃
- bookmaker ?붿냼瑜??섏씠吏 濡쒕뱶 ????踰덈쭔 pre-fetch?섏뿬 stale element 諛⑹?
- headless 紐⑤뱶 ?ъ슜 (ActionChains ?대┃?쇰줈 ?앹뾽 ?몃━嫄??뺤씤??
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

CSV_PATH      = 'kbo_odds.csv'
FILL_FROM     = '2026-04-22'
RESTART_EVERY = 3

df = pd.read_csv(CSV_PATH)

# open ?녿뒗 寃쎄린 ???(Momobet/Roobet/Stake.com/VOBET? ?앹뾽 ?놁쓬 ???쒖쇅)
NO_POPUP_BMS = {'Momobet', 'Roobet', 'Stake.com', 'VOBET'}
target_ids = set(
    df[(df['home_open'].isna()) & (df['date'] >= FILL_FROM)
       & ~df['bookmaker'].isin(NO_POPUP_BMS)]['match_id'].unique()
)
print(f'open ?섏쭛 ??? {len(target_ids)}寃쎄린')

driver = get_driver()
updated = 0

try:
    print('寃쎄린 URL 紐⑸줉 ?섏쭛 以?..')
    match_list = get_match_urls(driver, stop_before=FILL_FROM)
    target_matches = [m for m in match_list if m['match_id'] in target_ids and m['finished']]
    print(f'URL 留ㅼ묶 ?꾨즺: {len(target_matches)}寃쎄린')

    for idx, match in enumerate(target_matches):
        if idx > 0 and idx % RESTART_EVERY == 0:
            print(f'\n  [?쒕씪?대쾭 ?ъ떆?? {idx}/{len(target_matches)}寃쎄린 ?꾨즺...')
            try: driver.quit()
            except: pass
            driver = get_driver()
            time.sleep(2)

        norm_date = normalize_date(match['date'])
        mid = match['match_id']
        print(f'\n?섏쭛: {norm_date} {match["home"]} vs {match["away"]}')

        driver.get(match['url'])
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'p.height-content.pl-4')))
        except:
            print('  ??濡쒕뵫 ?ㅽ뙣')
            continue
        time.sleep(3)

        # bookmaker ?붿냼 ??踰덉뿉 pre-fetch
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
                print(f'  {bm} ?ㅻ쪟: {e}')
                continue

        print(f'  ??{match_updated}媛?遺곷찓?댁빱 ?낅뜲?댄듃')
        updated += match_updated
        time.sleep(1)

except Exception as e:
    print(f'?ㅻ쪟: {e}')
    import traceback; traceback.print_exc()

finally:
    try: driver.quit()
    except: pass

if updated > 0:
    df = recalc_winner_direction(df)
    # consensus ?꾨씫 蹂댁젙: home_close/away_close ?덇퀬 consensus NaN????梨꾩?
    cons_mask = df['home_close'].notna() & df['away_close'].notna() & df['consensus'].isna()
    if cons_mask.any():
        df.loc[cons_mask, 'consensus'] = df.loc[cons_mask].apply(
            lambda r: 'home' if r['home_close'] < r['away_close'] else 'away', axis=1)
        print(f'consensus 蹂댁젙: {cons_mask.sum()}嫄?)
    df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'\n?꾨즺: {updated}媛?遺곷찓?댁빱 open ?곗씠???낅뜲?댄듃 ??{CSV_PATH} ???)
else:
    print('\n?낅뜲?댄듃 ?놁쓬')
