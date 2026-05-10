---
description: 스냅샷 기준으로 검증 실행 후 Streamlit 백테스트 업데이트 및 git push
---

스냅샷 기준으로 예측 검증을 실행하고 Streamlit 백테스트(kbo_verify_log.csv)를 업데이트합니다.

다음 단계를 순서대로 실행하세요:

1. kbo_predictions.json의 pred_date를 확인합니다.
2. `snapshots/kbo_predictions_{pred_date}.json` 스냅샷이 존재하는지 확인합니다. 없으면 "스냅샷이 없습니다. 먼저 /sns를 실행하세요." 라고 알립니다.
3. `python verification/kbo_verify.py` 를 실행합니다. (verify.py가 자동으로 스냅샷을 읽습니다)
4. kbo_verify_log.csv에서 해당 날짜 결과를 읽어 슬롯별 예측/실제/적중 여부를 표로 출력합니다.
5. 전체 적중률도 출력합니다.
6. git add kbo_verify_log.csv + commit + push 합니다. 커밋 메시지: "kbo_verify_log: {pred_date} 검증 결과 업데이트"
