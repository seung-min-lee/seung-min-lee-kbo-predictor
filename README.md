# KBO 승패 예측 모델 (배당 변동 패턴 기반)

## 개요
오즈포탈(OddsPortal) 북메이커 배당 변동 패턴을 분석하여 KBO 경기 승패를 예측하는 모델입니다.
충북대학교 캡스톤디자인 프로젝트 (2026)

## 연구 목적
북메이커들의 배당 변동 방향(상승/하락)에는 시계열 패턴이 존재하며,
이 패턴으로 다음 경기 승패를 예측할 수 있다는 가설을 검증합니다.

## 시스템 구성
| 파일 | 역할 |
|------|------|
| `kbo_update.py` | OddsPortal에서 경기 배당 데이터 수집 |
| `kbo_predict.py` | 배당 패턴 분석 및 승패 예측 |
| `kbo_verify.py`  | 예측 결과 자동 검증 및 성능 지표 산출 |
| `kbo_schedule.py`| 매일 22:30 자동 실행 스케줄러 |

## 데이터 구조
- 수집 대상: OddsPortal KBO 결과 페이지
- 북메이커: 15개 (BetInAsia, 1xBet, Alphabet 등)
- 피처: 홈/원정팀 배당 open/close/change/direction, 배당비율, 합의도
- 수집 제외: 무승부, 취소(Postp.) 경기

## 패턴 분석 방법
- Mirror 패턴, 반복블록, 연속블록, 대칭, 반접기 등
- 북메이커별 방향 벡터 투표로 최종 예측
- RandomForest ML 모델 보조 예측

## 자동화
GitHub Actions를 통해 매일 KST 22:30 자동 실행
(월요일 제외 - KBO 휴식일)

## 실행 방법
```bash
# 데이터 수집
python kbo_update.py

# 예측
python kbo_predict.py

# 검증
python kbo_verify.py
```

## 요구사항
```
selenium
webdriver-manager
pandas
scikit-learn
schedule
```
