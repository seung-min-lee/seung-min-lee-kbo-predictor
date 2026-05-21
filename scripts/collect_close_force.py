"""
오늘 경기 bm_close 강제 재수집 (스킵 조건 없음)
bm_open은 유지하고 bm_close만 덮어씀
사용: python scripts/collect_close_force.py
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json, time
from collect_today_odds_selenium import (
    make_driver, get_today_match_urls, scrape_bm_current_odds, TODAY
)

TODAY_ODDS_PATH = 'kbo_today_odds.json'


def main():
    print(f'bm_close 강제 재수집: {TODAY}')

    with open(TODAY_ODDS_PATH, encoding='utf-8') as f:
        today_odds = json.load(f)

    driver = make_driver()
    try:
        print('경기 목록 수집 중...')
        match_list = get_today_match_urls(driver)
        print(f'오늘 경기 {len(match_list)}개')
    finally:
        try:
            driver.quit()
        except:
            pass

    if not match_list:
        print('경기 URL 수집 실패')
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

        print(f'\n[slot{i}] {m["home"]} vs {m["away"]} (강제 재수집)')
        print(f'  URL: {m["url"]}')

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

        print(f'  BM {len(bm_data)}개 수집')

        if bm_data:
            # bm_open은 유지, bm_close만 갱신
            if 'bm_open' not in entry:
                entry['bm_open'] = entry.get('bm_close', bm_data)
            entry['bm_close'] = bm_data
            entry['match_url'] = m['url']
            h_avg = round(sum(v['home'] for v in bm_data.values()) / len(bm_data), 3)
            a_avg = round(sum(v['away'] for v in bm_data.values()) / len(bm_data), 3)
            entry['home_odds'] = h_avg
            entry['away_odds'] = a_avg

            # open vs close 변동 요약
            open_data = entry.get('bm_open', {})
            moved = [(bm, round(bm_data[bm]['home'] - open_data[bm]['home'], 3))
                     for bm in bm_data if bm in open_data
                     and round(bm_data[bm]['home'] - open_data[bm]['home'], 3) != 0]
            if moved:
                print(f'  변동 BM: {len(moved)}개')
                for bm, chg in moved[:5]:
                    print(f'    {bm}: HOME {chg:+.3f}')
            else:
                print(f'  변동 없음 (open=close)')

        today_odds[entry_key] = entry
        with open(TODAY_ODDS_PATH, 'w', encoding='utf-8') as f:
            json.dump(today_odds, f, ensure_ascii=False, indent=2)
        print(f'  저장 완료')

    print(f'\n=== close 재수집 완료 ===')
    for k, v in sorted(today_odds.items()):
        if v.get('date') != TODAY:
            continue
        open_d = v.get('bm_open', {})
        close_d = v.get('bm_close', {})
        moved_count = sum(
            1 for bm in close_d
            if bm in open_d and round(close_d[bm]['home'] - open_d[bm]['home'], 3) != 0
        )
        print(f"  slot{int(v.get('slot',0))} {v['home']} vs {v['away']}: {len(close_d)}BM  변동{moved_count}개  H={v.get('home_odds')} A={v.get('away_odds')}")


if __name__ == '__main__':
    main()
