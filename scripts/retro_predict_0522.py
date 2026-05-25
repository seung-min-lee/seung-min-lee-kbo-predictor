"""05-21까지 데이터 기준으로 05-22 경기 retroactive 예측"""
import sys, os, shutil, json
sys.stdout.reconfigure(encoding='utf-8')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_root)

import pandas as pd

CUTOFF   = '2026-05-21'
PRED_DATE = '2026-05-22'
ODDS_PATH  = 'kbo_odds.csv'
GAMES_PATH = 'kbo_games.csv'
SNAP_PATH  = f'snapshots/kbo_predictions_{PRED_DATE}.json'

# ── 1. 기존 스냅샷 내용 확인 (05-21 경기면 덮어쓰기)
if os.path.exists(SNAP_PATH):
    with open(SNAP_PATH, encoding='utf-8') as f:
        _existing = json.load(f)
    slot_dates = [v.get('pred_date') for k, v in _existing.items()
                  if k.startswith('slot') and isinstance(v, dict)]
    if all(d == PRED_DATE for d in slot_dates if d):
        print(f'이미 올바른 스냅샷 존재: {SNAP_PATH}')
        sys.exit(0)
    print(f'기존 스냅샷은 {set(slot_dates)} 예측 → 덮어쓰기 진행')

# ── 2. 원본 백업
shutil.copy(ODDS_PATH,  ODDS_PATH  + '.retro_bak')
shutil.copy(GAMES_PATH, GAMES_PATH + '.retro_bak')
print('원본 백업 완료')

try:
    # ── 3. kbo_odds.csv → CUTOFF 이하만 남기기
    df_odds = pd.read_csv(ODDS_PATH)
    df_odds_cut = df_odds[df_odds['date'] <= CUTOFF].copy()
    df_odds_cut.to_csv(ODDS_PATH, index=False)
    print(f'kbo_odds.csv 필터: {len(df_odds_cut)}행 (≤{CUTOFF})')

    # ── 4. kbo_games.csv → 05-22 경기 winner 지우기 (미래 경기처럼)
    df_games = pd.read_csv(GAMES_PATH)
    mask_0522 = df_games['date'] == PRED_DATE
    df_games.loc[mask_0522, 'winner'] = None
    df_games.loc[mask_0522, 'winner_is_home'] = None
    df_games.to_csv(GAMES_PATH, index=False)
    print(f'kbo_games.csv: 05-22 winner 초기화 ({mask_0522.sum()}경기)')

    # ── 5. kbo_predict.py 실행
    import subprocess
    result = subprocess.run(
        [sys.executable, 'kbo_predict.py'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        cwd=_root
    )
    print('--- kbo_predict.py 출력 ---')
    print(result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
    if result.returncode != 0:
        print('STDERR:', result.stderr[:500])

    # ── 6. 생성된 kbo_predictions.json 확인 및 스냅샷 저장
    with open('kbo_predictions.json', encoding='utf-8') as f:
        pred = json.load(f)

    # pred_date는 각 슬롯 내부에 저장됨 (top-level 없음)
    first_slot = next((v for k, v in pred.items() if k.startswith('slot') and isinstance(v, dict)), {})
    actual_pred_date = first_slot.get('pred_date')
    print(f'\npred_date in json (slot): {actual_pred_date}')

    # pred_date 강제 수정
    if actual_pred_date != PRED_DATE:
        print(f'경고: pred_date={actual_pred_date} (예상: {PRED_DATE}), 강제 수정')
        for k in list(pred.keys()):
            if k.startswith('slot') and isinstance(pred[k], dict):
                pred[k]['pred_date'] = PRED_DATE
        with open('kbo_predictions.json', 'w', encoding='utf-8') as f:
            json.dump(pred, f, ensure_ascii=False, indent=2)
        print('pred_date 강제 수정 완료')

    shutil.copy('kbo_predictions.json', SNAP_PATH)
    print(f'\n스냅샷 저장: {SNAP_PATH}')

    # 슬롯별 예측 출력
    for k in sorted(pred.keys()):
        if not k.startswith('slot'):
            continue
        v = pred[k]
        home = v.get('home', '')
        away = v.get('away', '')
        rec  = v.get('final_rec', '')
        team = v.get('rec_team', '')
        print(f'  {k}: {home} vs {away} → {rec} ({team})')

finally:
    # ── 7. 원본 복원
    shutil.copy(ODDS_PATH  + '.retro_bak', ODDS_PATH)
    shutil.copy(GAMES_PATH + '.retro_bak', GAMES_PATH)
    os.remove(ODDS_PATH  + '.retro_bak')
    os.remove(GAMES_PATH + '.retro_bak')
    print('\n원본 복원 완료')
