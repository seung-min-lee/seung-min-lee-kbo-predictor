---
description: 현재 예측을 날짜별 스냅샷으로 저장하고 git push
---

현재 kbo_predictions.json을 날짜별 스냅샷으로 저장합니다.

다음 단계를 순서대로 실행하세요:

1. kbo_predict.py를 실행해서 최신 예측을 생성합니다.
2. predictions.json의 pred_date를 확인합니다.
3. `snapshots/kbo_predictions_{pred_date}.json` 파일이 이미 존재하는지 확인합니다.
4. 존재하지 않으면 저장합니다. 이미 존재하면 "이미 스냅샷이 존재합니다: {파일명}" 을 알립니다.
5. 저장된 스냅샷 파일명과 슬롯별 예측 결과(팀명 + HOME/AWAY)를 출력합니다.
6. git add + commit + push 합니다. 커밋 메시지: "스냅샷 저장: {pred_date}"
