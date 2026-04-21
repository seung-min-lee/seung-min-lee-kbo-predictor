import json
import pandas as pd
import os
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

PRED_PATH   = 'kbo_predictions.json'
RESULT_PATH = 'kbo_verify_log.csv'
CSV_PATH    = 'kbo_odds.csv'

# ── 로드 ─────────────────────────────────────────────
if not os.path.exists(PRED_PATH):
    print('예측 파일 없음. 먼저 kbo_predict.py 실행해주세요.')
    exit()

with open(PRED_PATH, 'r', encoding='utf-8') as f:
    predictions = json.load(f)

df = pd.read_csv(CSV_PATH)
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)

if os.path.exists(RESULT_PATH):
    log_df = pd.read_csv(RESULT_PATH)
else:
    log_df = pd.DataFrame(columns=[
        'date', 'slot', 'home', 'away',
        'prediction', 'actual_winner',
        'correct', 'confidence',
        'ml_home_prob', 'ml_away_prob'
    ])

print('='*60)
print('자동 검증 시스템')
print('='*60)

new_rows = []

for key, pred in predictions.items():
    slot = pred['slot']
    rec  = pred['recommendation']

    if rec == 'PASS':
        continue
    if pred.get('verified'):
        continue

    # 예측 값 (1=홈승, 0=원정승)
    pred_val = 1 if rec == 'HOME(1)' else 0

    # CSV에서 해당 슬롯의 가장 최신 경기 결과 찾기
    slot_df = df[df['slot'] == slot].copy()
    if len(slot_df) == 0:
        print(f'[SLOT {slot}] 데이터 없음 → 스킵')
        continue

    # 예측 당시 마지막 날짜보다 이후 경기 (새로 추가된 경기)
    # predictions에 저장된 consensus_seq 길이 = 예측 당시 경기 수
    pred_game_count = len(pred.get('consensus_seq', []))
    dates_sorted = sorted(slot_df['date_order'].unique())

    # 예측 당시보다 새로운 날짜가 있는지 확인
    if len(dates_sorted) <= pred_game_count:
        print(f'[SLOT {slot}] 아직 결과 없음 (현재 {len(dates_sorted)}경기, 예측시 {pred_game_count}경기)')
        continue

    # 예측 대상: pred_game_count번째 날짜 (0-indexed)
    target_date_order = dates_sorted[pred_game_count]
    target_df = slot_df[slot_df['date_order'] == target_date_order]

    if len(target_df) == 0:
        print(f'[SLOT {slot}] 대상 경기 데이터 없음')
        continue

    target = target_df.iloc[0]
    home   = target['home']
    away   = target['away']
    winner = target['winner']

    # 실제 결과
    actual_val = 1 if winner == home else 0
    actual_str = 'HOME(1)' if actual_val == 1 else 'AWAY(0)'
    correct    = (pred_val == actual_val)
    status     = 'O' if correct else 'X'

    print(f'\n[SLOT {slot}] {home} vs {away}')
    print(f'  예측:    {rec}')
    print(f'  실제:    {actual_str} ({winner} 승)')
    print(f'  결과:    {status}')
    print(f'  신뢰도:  {pred["confidence"]:.1%}')

    pred['verified']  = True
    pred['actual']    = actual_str
    pred['correct']   = correct

    new_rows.append({
        'date':          datetime.now().strftime('%Y-%m-%d'),
        'slot':          slot,
        'home':          home,
        'away':          away,
        'prediction':    rec,
        'actual_winner': actual_str,
        'correct':       correct,
        'confidence':    pred['confidence'],
        'ml_home_prob':  pred.get('ml_home_prob', 0.5),
        'ml_away_prob':  pred.get('ml_away_prob', 0.5),
    })

# ── 저장 ─────────────────────────────────────────────
if new_rows:
    new_df = pd.DataFrame(new_rows)
    log_df = pd.concat([log_df, new_df], ignore_index=True)
    log_df.to_csv(RESULT_PATH, index=False, encoding='utf-8-sig')

    with open(PRED_PATH, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)

    print(f'\n{len(new_rows)}개 검증 완료 → {RESULT_PATH} 저장')
else:
    print('\n새로 검증할 경기 없음')

# ── 성능 지표 ─────────────────────────────────────────
print('\n' + '='*60)
print('모델 성능 지표')
print('='*60)

if len(log_df) == 0:
    print('검증 데이터 없음')
else:
    total   = len(log_df)
    correct = log_df['correct'].sum()
    acc     = correct / total

    print(f'\n전체:  {int(correct)}/{total} ({acc:.1%})')

    # 슬롯별
    print(f'\n슬롯별 정확도:')
    for slot in sorted(log_df['slot'].unique()):
        s   = log_df[log_df['slot']==slot]
        s_acc = s['correct'].sum() / len(s)
        bar = 'O'*int(s['correct'].sum()) + 'X'*(len(s)-int(s['correct'].sum()))
        print(f'  SLOT {slot}: {int(s["correct"].sum())}/{len(s)} ({s_acc:.1%})  [{bar}]')

    # 신뢰도별
    print(f'\n신뢰도별 정확도:')
    bins   = [0, 0.6, 0.7, 0.8, 0.9, 1.01]
    labels = ['~60%','60~70%','70~80%','80~90%','90%~']
    log_df['conf_bin'] = pd.cut(log_df['confidence'], bins=bins, labels=labels)
    for lbl in labels:
        b = log_df[log_df['conf_bin']==lbl]
        if len(b) == 0: continue
        b_acc = b['correct'].sum() / len(b)
        print(f'  {lbl:8s}: {int(b["correct"].sum())}/{len(b)} ({b_acc:.1%})')

    # 최근 흐름
    print(f'\n최근 예측 흐름:')
    for _, row in log_df.tail(10).iterrows():
        mark = 'O' if row['correct'] else 'X'
        print(f'  [{mark}] SLOT{int(row["slot"])} '
              f'{row["home"]} vs {row["away"]} | '
              f'예측:{row["prediction"]} 실제:{row["actual_winner"]} | '
              f'신뢰도:{row["confidence"]:.0%}')

    # 연속 흐름
    results = log_df['correct'].tolist()
    if results:
        streak = 1
        for i in range(len(results)-1, 0, -1):
            if results[i] == results[i-1]: streak += 1
            else: break
        streak_type = '연속 정답' if results[-1] else '연속 오답'
        print(f'\n현재: {streak_type} {streak}연속')

    # 전체 흐름 시각화
    flow = ''.join('O' if r else 'X' for r in results)
    print(f'전체 흐름: [{flow}]')