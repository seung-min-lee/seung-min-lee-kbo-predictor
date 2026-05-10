# KBO 승패 예측 모델 (배당 변동 패턴 기반)

## 개요
오즈포탈(OddsPortal) 북메이커 배당 변동 패턴을 분석하여 KBO 경기 승패를 예측하는 모델입니다.  
AI빅데이터공학과 캡스톤디자인 프로젝트 (2026)

## 연구 배경
초기 모델은 모든 경기 승패 요인을 변수로 설계한 MLB 승패 예측 모델이였으며, 스포츠 특성상 선수 컨디션·운 등 수집 불가 요소가 더 크게 작용한다고 판단하였습니다. 이에 북메이커 배당 변동 방향의 시계열 패턴만으로 승패를 예측하는 모델을 연구합니다.

---

## 프로젝트 구조

```
kbo-predictor/
│
├── 프론트엔드 (Frontend)
│   └── kbo_app.py              # Streamlit 대시보드: 예측 결과 시각화, 시퀀스 표시
│
├── 패턴 예측 엔진 (Pattern Prediction)
│   ├── kbo_predict.py          # 핵심 예측 엔진: 배당 패턴 분석 + 투표 기반 승패 예측
│   ├── kbo_backtest.py         # 백테스트: 과거 날짜 전체 예측 정확도 검증
│   └── kbo_pattern_accuracy.py # 패턴 유형별 적중률 누적 기록 (학습용)
│
├── 데이터 수집 (Data Collection)
│   ├── kbo_update.py           # OddsPortal → kbo_odds.csv 전일 배당 자동 수집
│   ├── kbo_today_scrape.py     # 오늘 경기 개장/종가 배당 수집 → kbo_today_odds.json
│   ├── kbo_playwright_scrape.py# Playwright 기반 배당 수집 (셀레니움 대안)
│   ├── kbo_fill_open.py        # 누락된 개장(open) 배당 보완 수집
│   ├── kbo_retry_missing.py    # NaN 배당 재수집
│   ├── collect_today.py        # 오늘 경기 배당 수집 보조
│   └── collect_today_bm.py     # 북메이커별 오늘 배당 수집
│
├── 스케줄 / 자동화 (Scheduling)
│   ├── kbo_schedule.py         # 매일 KST 22:30 자동 실행 스케줄러
│   └── kbo_games.py            # kbo_games.csv 경기 결과 생성 및 갱신
│
├── 검증 / 분석 (Verification & Analysis)
│   ├── kbo_verify.py           # 예측 vs 실제 결과 자동 검증
│   ├── validate_odds.py        # 수집된 배당 데이터 유효성 검사
│   ├── check_live_odds.py      # 실시간 배당 확인
│   ├── check_slot4.py          # 슬롯4 데이터 점검
│   ├── check_slots.py          # 전체 슬롯 데이터 점검
│   └── check_today_order.py    # 오늘 경기 순서 확인
│
├── 디버그 스크립트 (Debug)
│   ├── debug_match_page.py     # 매치 페이지 파싱 디버그
│   ├── debug_odds.py           # 배당 수집 디버그
│   ├── debug_popup.py          # OddsPortal 팝업 동작 디버그
│   └── debug_scrape.py         # 스크래핑 디버그
│
├── 테스트 / 일회성 스크립트 (Tests / One-off)
│   ├── test_momobet.py         # Momobet BM 수집 테스트
│   ├── test_pw.py              # Playwright 동작 테스트
│   ├── test_recollect.py       # 재수집 테스트
│   ├── test_single.py          # 단일 경기 수집 테스트
│   ├── next_matches_test.py    # 다음 경기 매핑 테스트
│   ├── recollect_0506.py       # 05-06 데이터 재수집 (일회성)
│   ├── recollect_0506_partial.py
│   ├── recollect_range.py      # 날짜 범위 재수집
│   ├── scrape_0508_verify.py   # 05-08 배당 3회 검증 수집
│   ├── scrape_0508_retry4.py   # 05-08 재시도 수집 (Playwright)
│   ├── scrape_0508_selenium4.py# 05-08 재시도 수집 (Selenium)
│   ├── scrape_all_nan.py       # 전체 NaN 배당 수집
│   └── scrape_nan_verify.py    # NaN 배당 3회 검증 수집
│
└── 데이터 파일 (Data)
    ├── kbo_odds.csv             # 북메이커별 배당 데이터 (open/close/change/direction)
    ├── kbo_games.csv            # 경기 결과 (승패, winner_is_home)
    ├── kbo_today_odds.json      # 오늘 경기 실시간 배당
    ├── kbo_predictions.json     # 오늘 예측 결과 + 패턴 로그
    ├── kbo_verify_log.csv       # 예측 정확도 로그
    └── pattern_accuracy.json    # 패턴 유형별 누적 적중률 (자동 생성)
```

---

## 패턴 분석 방법

### 탐지 패턴 유형
| 패턴 | 설명 | 예시 |
|------|------|------|
| Mirror | 끝 N개가 앞 N개의 반전 | `[1,0,0,1]` → `1` |
| 꼬리미러 | 시퀀스 끝 부분이 분할 미러 구조 | `[1,1,0,0,1]` → `1` |
| 팰린드롬확장 | 끝이 팰린드롬 구조로 확장 중 | `[1,1,1,0,1,1]` → `1` |
| 교차쌍 | 같은 값 쌍이 교대 | `[1,1,0,0,1]` → `1` |
| 반복블록 | N개 블록 반복 | `[1,0,1,0,1]` → `0` |
| 계단식 | 런 길이가 등차 변화 | — |
| Fold+꼬리 | 접기 미러 후 꼬리 패턴 | — |
| 롤링모멘텀 | 최근 N개 모멘텀 지속 | — |

### 예측 흐름
```
배당 수집 → 시퀀스 구성 → 패턴 탐지(투표) → 다수결 집계
→ 슬롯 정배/역배 패턴 결합 → BM 방향 보정 → 최종 추천
→ ML(RandomForest) 보조
```

---

## 데이터 파이프라인

```
[매일 22:30]
kbo_update.py  →  kbo_odds.csv
kbo_games.py   →  kbo_games.csv
kbo_predict.py →  kbo_predictions.json
kbo_verify.py  →  kbo_verify_log.csv

[경기 결과 후]
kbo_pattern_accuracy.py → pattern_accuracy.json  (패턴 학습 기록)
```

---

## 실행 방법

```bash
# 배당 데이터 수집
python kbo_update.py

# 예측 실행
python kbo_predict.py

# 검증
python kbo_verify.py

# Streamlit 대시보드 실행
streamlit run kbo_app.py

# 경기 결과 후 패턴 적중률 업데이트
python kbo_pattern_accuracy.py
```

---

## 요구사항

```
playwright
selenium
webdriver-manager
pandas
scikit-learn
streamlit
schedule
```

---

## 자동화
- GitHub Actions: 매일 KST 22:30 자동 실행 (월요일 제외, KBO 휴식일)
- Streamlit Cloud: 대시보드 상시 배포
