"""
05-16 결과 반영:
1. kbo_games.csv 슬롯/결과 업데이트
2. kbo_odds.csv 기존 05-16 제거 후 올바른 결과로 재삽입
3. winner_direction 계산
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json, numpy as np, pandas as pd

DATE = '2026-05-16'

# 확인된 결과
RESULTS = {
    1.0: {'home': 'KT Wiz Suwon',   'away': 'Hanwha Eagles',  'winner': 'Hanwha Eagles',  'wih': False, 'match_id': 'S0DrbHCk'},
    2.0: {'home': 'Doosan Bears',    'away': 'Lotte Giants',   'winner': 'Doosan Bears',   'wih': True,  'match_id': 'Aonqhgqt'},
    3.0: {'home': 'Samsung Lions',   'away': 'KIA Tigers',     'winner': 'Samsung Lions',  'wih': True,  'match_id': 'z3Y35aKF'},
    4.0: {'home': 'NC Dinos',        'away': 'Kiwoom Heroes',  'winner': 'NC Dinos',       'wih': True,  'match_id': 'rTyC3wkS'},
    5.0: {'home': 'SSG Landers',     'away': 'LG Twins',       'winner': 'SSG Landers',    'wih': True,  'match_id': 'Uk337Lk3'},
}

# ── kbo_games.csv 업데이트 ────────────────────────────────────────────
games = pd.read_csv('kbo_games.csv')

# 05-16 행 제거 후 재생성
games = games[games['date'] != DATE].copy()

new_game_rows = []
for slot, r in sorted(RESULTS.items()):
    new_game_rows.append({
        'date':           DATE,
        'slot':           slot,
        'home':           r['home'],
        'away':           r['away'],
        'winner':         r['winner'],
        'winner_is_home': r['wih'],
    })

new_games_df = pd.DataFrame(new_game_rows)
for col in games.columns:
    if col not in new_games_df.columns:
        new_games_df[col] = float('nan')
new_games_df = new_games_df[games.columns]

games = pd.concat([games, new_games_df], ignore_index=True)
games.to_csv('kbo_games.csv', index=False)
print(f"kbo_games.csv 업데이트: 05-16 {len(new_game_rows)}경기")

# ── kbo_today_odds.json 로드 ─────────────────────────────────────────
with open('kbo_today_odds.json', encoding='utf-8') as f:
    today_json = json.load(f)

# ── winner_direction 계산 ─────────────────────────────────────────────
def calc_dir(ho, hc, ao, ac, wih):
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [ho, hc, ao, ac]):
            return np.nan
        if wih is None:
            return np.nan
        hchg = float(hc) - float(ho)
        achg = float(ac) - float(ao)
        wchg = hchg if wih else achg
        lchg = achg if wih else hchg
        if abs(wchg - lchg) < 0.001:
            return np.nan
        return 1.0 if wchg > lchg else 0.0
    except:
        return np.nan

# ── kbo_odds.csv 재삽입 ──────────────────────────────────────────────
odds_df = pd.read_csv('kbo_odds.csv')

# 기존 05-16 제거
existing_count = len(odds_df[odds_df['date'] == DATE])
if existing_count:
    print(f"기존 05-16 {existing_count}행 제거")
    odds_df = odds_df[odds_df['date'] != DATE].copy()

new_rows = []
for slot, r in sorted(RESULTS.items()):
    key = f"{DATE}|{int(slot)}|{r['home']}|{r['away']}"
    if key not in today_json:
        print(f"slot{int(slot)}: JSON 키 없음 ({key})")
        continue

    sd = today_json[key]
    bm_open = sd.get('bm_open', {})
    bm_close = sd.get('bm_close', {})

    wih = r['wih']

    # slot1 close는 라이브배당(무효) → NaN
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

        hchg = round(float(hc) - float(ho), 3) if (ho is not None and hc is not None) else float('nan')
        achg = round(float(ac) - float(ao), 3) if (ao is not None and ac is not None) else float('nan')
        wd = calc_dir(ho, hc, ao, ac, wih)

        new_rows.append({
            'date':           DATE,
            'slot':           slot,
            'home':           r['home'],
            'away':           r['away'],
            'match_id':       r['match_id'],
            'bookmaker':      bm,
            'home_open':      float(ho) if ho is not None else float('nan'),
            'home_close':     float(hc) if hc is not None else float('nan'),
            'away_open':      float(ao) if ao is not None else float('nan'),
            'away_close':     float(ac) if ac is not None else float('nan'),
            'home_change':    hchg,
            'away_change':    achg,
            'winner':         r['winner'],
            'winner_is_home': wih,
            'winner_direction': wd,
        })

new_df = pd.DataFrame(new_rows)

for col in odds_df.columns:
    if col not in new_df.columns:
        new_df[col] = float('nan')
new_df = new_df[odds_df.columns]

final_df = pd.concat([odds_df, new_df], ignore_index=True)
final_df.to_csv('kbo_odds.csv', index=False)
print(f"kbo_odds.csv 저장 완료: {len(final_df)}행 (추가: {len(new_df)}행)")

# ── 요약 ─────────────────────────────────────────────────────────────
print()
print("=== 05-16 삽입 요약 ===")
for slot in sorted(RESULTS):
    r = RESULTS[slot]
    mask = (new_df['slot'] == slot)
    s = new_df[mask]
    bm_count = len(s)
    close_count = s['home_close'].notna().sum()
    wd_count = s['winner_direction'].notna().sum()
    wd_1 = (s['winner_direction'] == 1).sum()
    wd_0 = (s['winner_direction'] == 0).sum()
    print(f"  slot{int(slot)} {r['home']} vs {r['away']} → {r['winner']}")
    print(f"    {bm_count}BM | close={close_count} | wd={wd_count} (1:{wd_1} 0:{wd_0})")
