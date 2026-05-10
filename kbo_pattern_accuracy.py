"""패턴 적중률 누적 기록기
오늘 경기 결과가 나오면 실행: python kbo_pattern_accuracy.py
kbo_predictions.json 의 home/away_pattern_log 를 읽어
pattern_accuracy.json 에 패턴 유형별 성공/실패 누적.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json, os, pandas as pd
from datetime import datetime

PRED_PATH    = 'kbo_predictions.json'
GAMES_PATH   = 'kbo_games.csv'
ACC_PATH     = 'pattern_accuracy.json'
GAME_LOG_PATH = 'pattern_game_log.json'


def load_accuracy():
    if os.path.exists(ACC_PATH):
        with open(ACC_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_accuracy(data):
    with open(ACC_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_game_log():
    if os.path.exists(GAME_LOG_PATH):
        with open(GAME_LOG_PATH, encoding='utf-8') as f:
            return json.load(f)
    return []


def save_game_log(data):
    with open(GAME_LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update(pred_date=None):
    # 예측 로드
    if not os.path.exists(PRED_PATH):
        print('kbo_predictions.json 없음'); return
    with open(PRED_PATH, encoding='utf-8') as f:
        predictions = json.load(f)

    # 날짜 결정
    if pred_date is None:
        dates = {v.get('pred_date') for v in predictions.values() if v.get('pred_date')}
        if not dates:
            print('예측 날짜 없음'); return
        pred_date = max(dates)
    print(f'패턴 정확도 업데이트: {pred_date}')

    # 실제 결과 로드
    games_df = pd.read_csv(GAMES_PATH)
    results_today = games_df[games_df['date'] == pred_date]
    if results_today.empty:
        print(f'{pred_date} 실제 결과 없음 — 경기 종료 후 실행하세요')
        return

    accuracy = load_accuracy()
    game_log = load_game_log()
    already_done = {(e['date'], e['slot']) for e in game_log}

    updated = 0
    for key, pred in predictions.items():
        slot       = pred.get('slot')
        home       = pred.get('home')
        away       = pred.get('away')
        rec_str    = pred.get('recommendation', 'PASS')
        p_date     = pred.get('pred_date', pred_date)

        if p_date != pred_date:
            continue
        if (p_date, slot) in already_done:
            continue

        # 실제 결과 찾기
        match = results_today[
            (results_today['home'] == home) & (results_today['away'] == away)
        ]
        if match.empty:
            continue

        actual_home_win = bool(match.iloc[0]['winner_is_home'])
        actual_winner   = home if actual_home_win else away

        if rec_str == 'PASS':
            final_correct = None
        elif rec_str.startswith('HOME'):
            final_correct = actual_home_win
        else:
            final_correct = not actual_home_win

        # 패턴 로그에서 적중 여부 기록
        h_log = pred.get('home_pattern_log', [])
        a_log = pred.get('away_pattern_log', [])
        h_win_rec = pred.get('home_win_rec')
        a_win_rec = pred.get('away_win_rec')

        # 홈팀 패턴들: pred==h_win_rec 이면 패턴이 최종 홈팀 예측에 동의
        # 실제 홈팀 승 여부(actual_home_win)와 비교
        for entry in h_log:
            ptype = entry['type']
            ppred = entry['pred']   # 1=홈팀 승 예측, 0=홈팀 패 예측
            correct = (ppred == 1) == actual_home_win
            if ptype not in accuracy:
                accuracy[ptype] = {'total': 0, 'correct': 0}
            accuracy[ptype]['total'] += 1
            if correct:
                accuracy[ptype]['correct'] += 1

        # 원정팀 패턴들: pred==a_win_rec 이면 패턴이 원정팀 승 예측에 동의
        # a_win_rec=1 → 원정팀 승 예측 → actual_home_win=False 이면 맞음
        for entry in a_log:
            ptype = entry['type']
            ppred = entry['pred']   # 1=원정팀 승 예측, 0=원정팀 패 예측
            correct = (ppred == 1) == (not actual_home_win)
            if ptype not in accuracy:
                accuracy[ptype] = {'total': 0, 'correct': 0}
            accuracy[ptype]['total'] += 1
            if correct:
                accuracy[ptype]['correct'] += 1

        game_log.append({
            'date': p_date, 'slot': slot, 'home': home, 'away': away,
            'recommendation': rec_str, 'actual_winner': actual_winner,
            'correct': final_correct,
            'home_patterns': [e['type'] for e in h_log],
            'away_patterns': [e['type'] for e in a_log],
        })
        updated += 1

    save_accuracy(accuracy)
    save_game_log(game_log)

    # 정확도 출력
    print(f'\n업데이트된 경기: {updated}')
    print(f'\n=== 패턴 유형별 적중률 ===')
    sorted_acc = sorted(accuracy.items(), key=lambda x: -x[1]['total'])
    for ptype, stats in sorted_acc:
        t = stats['total']
        c = stats['correct']
        print(f'  {ptype:<20} {c}/{t} ({c/t:.1%})')
    print(f'\n저장: {ACC_PATH}, {GAME_LOG_PATH}')


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    update(date_arg)
