"""05-22, 05-23, 05-24 예측 검증 일괄 실행"""
import sys, os, json, shutil
sys.stdout.reconfigure(encoding='utf-8')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_root)

PRED_PATH = 'kbo_predictions.json'
DATES = ['2026-05-22', '2026-05-23', '2026-05-24']

# 현재 predictions.json 백업
backup = None
if os.path.exists(PRED_PATH):
    with open(PRED_PATH, encoding='utf-8') as f:
        backup = f.read()

try:
    for date in DATES:
        snap_path = f'snapshots/kbo_predictions_{date}.json'
        if not os.path.exists(snap_path):
            print(f'[{date}] 스냅샷 없음 - 스킵')
            continue

        print(f'\n{"="*50}')
        print(f'검증: {date}')
        print(f'{"="*50}')

        # 스냅샷을 predictions.json으로 임시 복사
        shutil.copy(snap_path, PRED_PATH)

        # verify 실행
        import importlib.util, types
        # subprocess로 실행
        import subprocess
        result = subprocess.run(
            [sys.executable, 'verification/kbo_verify.py'],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        # 주요 출력만 필터링
        for line in result.stdout.splitlines():
            if any(x in line for x in ['SLOT', '적중', '스킵', '미입력', '결과', '전체', '최근']):
                print(line)
        if result.returncode != 0:
            print('STDERR:', result.stderr[:200])
finally:
    # 원본 복원
    if backup:
        with open(PRED_PATH, 'w', encoding='utf-8') as f:
            f.write(backup)

print('\n완료. kbo_verify_log.csv 업데이트됨')
