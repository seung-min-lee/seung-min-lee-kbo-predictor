import schedule
import time
import subprocess
from datetime import datetime

def run_daily():
    now = datetime.now()
    print(f'\n[{now.strftime("%Y-%m-%d %H:%M")}] 자동 실행 시작')

    # 1. 새 경기 결과 수집
    print('1. 경기 결과 수집 중...')
    subprocess.run(['python', 'kbo_update.py'])

    # 2. 예측 검증
    print('2. 예측 검증 중...')
    subprocess.run(['python', 'kbo_verify.py'])

    # 3. 다음 경기 예측
    print('3. 다음 경기 예측 중...')
    subprocess.run(['python', 'kbo_predict.py'])

    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M")}] 완료')

def should_run():
    """월요일(0) 제외하고 실행"""
    return datetime.now().weekday() != 0  # 0=월요일

def job():
    if should_run():
        run_daily()
    else:
        print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M")}] 월요일 → 스킵')

# 매일 22:30 실행
schedule.every().day.at("22:30").do(job)

print('='*50)
print('KBO 자동 스케줄러')
print('='*50)
print('실행 시간: 매일 22:30 (월요일 제외)')
print('Ctrl+C 로 중단')
print()

# 다음 실행 시간 출력
next_run = schedule.next_run()
print(f'다음 실행: {next_run.strftime("%Y-%m-%d %H:%M")}')

while True:
    schedule.run_pending()
    time.sleep(30)