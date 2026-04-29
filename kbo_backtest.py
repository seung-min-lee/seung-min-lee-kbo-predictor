"""
kbo_backtest.py
과거 경기에 대해 모델 예측 정확도를 사후 검증하여 kbo_verify_log.csv 생성
"""
import os, sys, traceback
import pandas as pd
import numpy as np

LOG_PATH = 'kbo_verify_log.csv'
MIN_HISTORY = 5

print('kbo_predict.py 함수 및 모델 로딩 중...')
ns = {'_BACKTEST_ONLY': True, '__file__': 'kbo_predict.py', '__name__': '__main__'}
with open('kbo_predict.py', encoding='utf-8') as f:
    src = f.read()
try:
    exec(compile(src, 'kbo_predict.py', 'exec'), ns)
except SystemExit:
    pass

game_df = ns['game_df']
df      = ns['df']
model   = ns['model']
X       = ns.get('X', [])

get_team_triple_seq = ns['get_team_triple_seq']
pat_rec             = ns['pat_rec']
analyze_pattern     = ns['analyze_pattern']
make_feat_team      = ns['make_feat_team']

print(f'로드 완료: {len(game_df)}경기, ML학습샘플={len(X)}')

completed = game_df[
    game_df['winner_is_home'].notna() &
    (game_df['winner'] != '취소')
].sort_values('date_order').copy()

print(f'검증 대상: {len(completed)}경기 ({completed["date"].min()} ~ {completed["date"].max()})')


def predict_game(home, away, date_order):
    h_dir, h_agr, h_fav_win, h_team_win = get_team_triple_seq(home, date_order)
    a_dir, a_agr, a_fav_win, a_team_win = get_team_triple_seq(away, date_order)

    h_win_rec, _ = pat_rec(h_team_win)
    a_win_rec, _ = pat_rec(a_team_win)

    home_pa    = analyze_pattern(h_team_win) if len(h_team_win) >= 3 else None
    away_pa    = analyze_pattern(a_team_win) if len(a_team_win) >= 3 else None
    home_score = home_pa['score'] if home_pa else 0.5
    away_score = away_pa['score'] if away_pa else 0.5

    final_rec = None
    conf      = 0.0

    if   h_win_rec == 1 and a_win_rec == 0:    final_rec = 1; conf = (home_score + away_score) / 2
    elif h_win_rec == 0 and a_win_rec == 1:    final_rec = 0; conf = (home_score + away_score) / 2
    elif h_win_rec == 1 and a_win_rec is None: final_rec = 1; conf = home_score * 0.8
    elif h_win_rec == 0 and a_win_rec is None: final_rec = 0; conf = home_score * 0.8
    elif h_win_rec is None and a_win_rec == 1: final_rec = 0; conf = away_score * 0.8
    elif h_win_rec is None and a_win_rec == 0: final_rec = 1; conf = away_score * 0.8

    feat = make_feat_team(home, away, date_order)
    try:
        ml_proba = model.predict_proba(np.array(feat).reshape(1, -1))[0]
    except Exception:
        ml_proba = [0.5, 0.5]

    if final_rec is None:
        if   ml_proba[1] >= 0.58: final_rec = 1; conf = float(ml_proba[1])
        elif ml_proba[0] >= 0.58: final_rec = 0; conf = float(ml_proba[0])

    return final_rec, round(conf, 3), round(float(ml_proba[1]), 3), round(float(ml_proba[0]), 3)


records = []
skipped = 0

for _, row in completed.iterrows():
    home            = row['home']
    away            = row['away']
    slot            = int(row['slot'])
    date            = row['date']
    date_order      = row['date_order']
    actual_home_win = bool(row['winner_is_home'])

    prior_h = game_df[
        ((game_df['home'] == home) | (game_df['away'] == home)) &
        (game_df['date_order'] < date_order)
    ]
    prior_a = game_df[
        ((game_df['home'] == away) | (game_df['away'] == away)) &
        (game_df['date_order'] < date_order)
    ]
    if len(prior_h) < MIN_HISTORY or len(prior_a) < MIN_HISTORY:
        skipped += 1
        continue

    try:
        rec, conf, ml_home, ml_away = predict_game(home, away, date_order)
    except Exception as e:
        print(f'  오류 {date} {home} vs {away}: {e}')
        continue

    if rec is None:
        prediction = 'PASS'
        correct    = None
    elif rec == 1:
        prediction = f'HOME({home})'
        correct    = actual_home_win
    else:
        prediction = f'AWAY({away})'
        correct    = not actual_home_win

    actual_winner = home if actual_home_win else away

    records.append({
        'date': date, 'slot': slot, 'home': home, 'away': away,
        'prediction': prediction, 'actual_winner': actual_winner,
        'correct': correct, 'confidence': conf,
        'ml_home_prob': ml_home, 'ml_away_prob': ml_away,
    })

log_df = pd.DataFrame(records)
log_df.to_csv(LOG_PATH, index=False, encoding='utf-8-sig')

total    = len(log_df)
has_pred = log_df[log_df['prediction'] != 'PASS']
n_pred   = len(has_pred)
n_ok     = int(has_pred['correct'].sum()) if n_pred > 0 else 0
acc      = n_ok / n_pred if n_pred > 0 else 0

print(f'\n=== 백테스트 결과 ===')
print(f'전체 검증: {total}  (이력부족 스킵: {skipped})')
print(f'예측: {n_pred}  PASS: {total - n_pred}')
print(f'정답: {n_ok}  정확도: {acc:.1%}')
print(f'저장: {LOG_PATH}')
