"""모든 스냅샷을 돌며 패턴 적중률을 백필 누적.
- snapshots/kbo_predictions_*.json 순회
- 각 날짜 예측의 home_pattern_log / away_pattern_log 와 실제 결과(kbo_games.csv) 비교
- pattern_accuracy.json + pattern_game_log.json 갱신
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, json, glob, re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

GAMES_PATH = 'kbo_games.csv'
ACC_PATH   = 'pattern_accuracy.json'
LOG_PATH   = 'pattern_game_log.json'
SNAP_GLOB  = 'snapshots/kbo_predictions_*.json'

games = pd.read_csv(GAMES_PATH)
games = games[games['winner_is_home'].notna()].copy()  # 결과 있는 경기만
games['key'] = games['date'].astype(str) + '|' + games['slot'].astype(float).astype(str) + '|' + games['home'] + '|' + games['away']

# 기존 누적 로드 (있으면)
accuracy = {}
if os.path.exists(ACC_PATH):
    with open(ACC_PATH, encoding='utf-8') as f:
        accuracy = json.load(f)
game_log = []
if os.path.exists(LOG_PATH):
    with open(LOG_PATH, encoding='utf-8') as f:
        game_log = json.load(f)

done_keys = {(e['date'], e['slot'], e['home'], e['away']) for e in game_log}

snap_files = sorted(glob.glob(SNAP_GLOB))
n_processed = 0
n_skipped   = 0

for sf in snap_files:
    m = re.search(r'(\d{4}-\d{2}-\d{2})\.json$', sf)
    if not m: continue
    snap_date = m.group(1)

    with open(sf, encoding='utf-8') as f:
        preds = json.load(f)

    g_today = games[games['date'] == snap_date]
    if g_today.empty:
        continue

    for sk, p in preds.items():
        slot = float(p.get('slot', 0))
        home = p.get('home')
        away = p.get('away')
        rec  = p.get('recommendation', 'PASS')
        if not home or not away:
            continue
        if (snap_date, slot, home, away) in done_keys:
            n_skipped += 1
            continue

        match = g_today[
            (g_today['home'] == home) & (g_today['away'] == away)
            & (g_today['slot'].astype(float) == slot)
        ]
        if match.empty:
            continue

        wih_val = match.iloc[0]['winner_is_home']
        if pd.isna(wih_val):
            continue
        actual_home_win = bool(wih_val)
        actual_winner = home if actual_home_win else away

        if rec == 'PASS':
            final_correct = None
        elif rec.startswith('HOME'):
            final_correct = actual_home_win
        else:
            final_correct = not actual_home_win

        h_log = p.get('home_pattern_log', []) or []
        a_log = p.get('away_pattern_log', []) or []

        for entry in h_log:
            ptype = entry.get('type', 'unknown')
            ppred = entry.get('pred')
            if ppred not in (0, 1): continue
            correct = (ppred == 1) == actual_home_win
            if ptype not in accuracy:
                accuracy[ptype] = {'total': 0, 'correct': 0}
            accuracy[ptype]['total'] += 1
            if correct: accuracy[ptype]['correct'] += 1

        for entry in a_log:
            ptype = entry.get('type', 'unknown')
            ppred = entry.get('pred')
            if ppred not in (0, 1): continue
            # away 패턴은 원정팀 승 예측 → not actual_home_win 과 비교
            correct = (ppred == 1) == (not actual_home_win)
            if ptype not in accuracy:
                accuracy[ptype] = {'total': 0, 'correct': 0}
            accuracy[ptype]['total'] += 1
            if correct: accuracy[ptype]['correct'] += 1

        game_log.append({
            'date': snap_date, 'slot': slot, 'home': home, 'away': away,
            'recommendation': rec, 'actual_winner': actual_winner,
            'correct': final_correct,
            'home_patterns': [e.get('type') for e in h_log],
            'away_patterns': [e.get('type') for e in a_log],
        })
        n_processed += 1

# 저장
with open(ACC_PATH, 'w', encoding='utf-8') as f:
    json.dump(accuracy, f, ensure_ascii=False, indent=2)
with open(LOG_PATH, 'w', encoding='utf-8') as f:
    json.dump(game_log, f, ensure_ascii=False, indent=2)

print(f'스냅샷 처리: {len(snap_files)}개')
print(f'신규 누적 경기: {n_processed}건, 스킵(중복): {n_skipped}건')
print(f'\n=== 패턴별 적중률 (top by total) ===')
sorted_acc = sorted(accuracy.items(), key=lambda x: -x[1]['total'])
print(f'{"패턴":<24} {"적중/총":<14} {"적중률":>8} {"라플라스":>10}')
print('-' * 60)
for ptype, st in sorted_acc:
    t, c = st['total'], st['correct']
    ratio = c/t if t else 0
    laplace = (c+1)/(t+2)
    print(f'{ptype:<24} {c:>4}/{t:<8} {ratio:>7.1%} {laplace:>9.3f}')
