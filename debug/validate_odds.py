"""
수집 후 데이터 검증 스크립트 (3가지 검증)
사용: python validate_odds.py [YYYY-MM-DD]  ← 날짜 생략 시 최근 7일
"""
import pandas as pd
import sys
from datetime import datetime, timedelta

CSV_PATH   = 'kbo_odds.csv'
GAMES_PATH = 'kbo_games.csv'

# 검증 날짜 범위
date_args = [a for a in sys.argv[1:] if not a.startswith('--')]
if len(date_args) >= 2:
    FROM, TO = date_args[0], date_args[1]
elif len(date_args) == 1:
    FROM = TO = date_args[0]
else:
    TO   = datetime.today().strftime('%Y-%m-%d')
    FROM = (datetime.today() - timedelta(days=7)).strftime('%Y-%m-%d')

print(f'검증 기간: {FROM} ~ {TO}\n')

df    = pd.read_csv(CSV_PATH)
games = pd.read_csv(GAMES_PATH)

sub = df[df['date'].between(FROM, TO)].copy()
if sub.empty:
    print('해당 기간 데이터 없음')
    sys.exit(0)

ok_total = fail_total = warn_total = 0

# ──────────────────────────────────────────────────────────────────
# 검증 1: 슬롯/팀 매핑 (kbo_games.csv 기준)
# ──────────────────────────────────────────────────────────────────
print('=' * 60)
print('검증 1: 슬롯/팀 매핑')
print('=' * 60)

games_clean = games[games['date'].str.match(r'^\d{4}-\d{2}-\d{2}$', na=False)].copy()
games_clean['slot'] = games_clean['slot'].astype(float)
games_sub = games_clean[games_clean['date'].between(FROM, TO)]

v1_ok = v1_fail = 0
for date in sorted(sub['date'].unique()):
    g = games_sub[games_sub['date'] == date]
    if g.empty:
        continue
    correct = {(r['home'], r['away']): int(r['slot']) for _, r in g.iterrows() if pd.notna(r['slot'])}
    odds_pairs = sub[sub['date'] == date][['slot', 'home', 'away']].drop_duplicates(['home', 'away'])
    for _, row in odds_pairs.iterrows():
        key = (row['home'], row['away'])
        if key not in correct:
            pass  # kbo_games.csv 미등재 → 슬롯 검증 불가, 스킵
        elif int(row['slot']) != correct[key]:
            print(f'  [{date}] {row["home"]} vs {row["away"]}: 슬롯 불일치 (odds={int(row["slot"])}, games={correct[key]})')
            v1_fail += 1
        else:
            v1_ok += 1

if v1_fail == 0:
    print(f'  OK 전체 {v1_ok}개 경기 슬롯 정상')
else:
    print(f'  NG {v1_fail}개 불일치, {v1_ok}개 정상')
ok_total += v1_ok; fail_total += v1_fail


# ──────────────────────────────────────────────────────────────────
# 검증 2: 배당 데이터 일관성
# ──────────────────────────────────────────────────────────────────
print()
print('=' * 60)
print('검증 2: 배당 데이터 일관성')
print('=' * 60)

v2_ok = v2_fail = v2_warn = 0

for _, row in sub.iterrows():
    label = f"[{row['date']} slot{int(row['slot'])} {row['bookmaker']}]"
    ho, hc = row.get('home_open'), row.get('home_close')
    ao, ac = row.get('away_open'), row.get('away_close')

    # (a) 값 범위 검사 (1.01 ~ 50)
    for val, name in [(ho,'home_open'),(hc,'home_close'),(ao,'away_open'),(ac,'away_close')]:
        if pd.isna(val):
            continue
        if val < 1.01 or val > 50:
            print(f'  NG {label} {name}={val} 범위 이상 (1.01~50)')
            v2_fail += 1

    # (b) open/close 역전 검사 (배당이 0.5 초과로 역전되면 수집 오류 의심)
    if pd.notna(ho) and pd.notna(hc):
        if abs(hc - ho) > 0.5:
            print(f'  WARN {label} home 배당 급변: open={ho} → close={hc} (Δ={hc-ho:+.2f})')
            v2_warn += 1
    if pd.notna(ao) and pd.notna(ac):
        if abs(ac - ao) > 0.5:
            print(f'  WARN {label} away 배당 급변: open={ao} → close={ac} (Δ={ac-ao:+.2f})')
            v2_warn += 1

    # (c) home/away 배당 합 (양쪽 close 있을 때) — 너무 낮으면 이상
    if pd.notna(hc) and pd.notna(ac):
        impl_prob = 1/hc + 1/ac
        if impl_prob < 1.02 or impl_prob > 1.30:
            print(f'  WARN {label} 내재확률 합 이상: {impl_prob:.3f} (h={hc}, a={ac})')
            v2_warn += 1
        else:
            v2_ok += 1

if v2_fail == 0 and v2_warn == 0:
    print(f'  OK {v2_ok}개 배당 쌍 정상')
else:
    print(f'  NG 오류 {v2_fail}개, 경고 {v2_warn}개, 정상 {v2_ok}개')
ok_total += v2_ok; fail_total += v2_fail; warn_total += v2_warn


# ──────────────────────────────────────────────────────────────────
# 검증 3: winner_direction 재계산 일치 여부
# ──────────────────────────────────────────────────────────────────
print()
print('=' * 60)
print('검증 3: winner_direction 재계산 검증')
print('=' * 60)

v3_ok = v3_fail = v3_skip = 0

for _, row in sub.iterrows():
    label = f"[{row['date']} slot{int(row['slot'])} {row['bookmaker']}]"
    ho, hc = row.get('home_open'), row.get('home_close')
    ao, ac = row.get('away_open'), row.get('away_close')
    wih    = row.get('winner_is_home')
    wd     = row.get('winner_direction')

    if pd.isna(ho) or pd.isna(hc) or pd.isna(ao) or pd.isna(ac) or pd.isna(wih):
        v3_skip += 1
        continue

    hchg = hc - ho
    achg = ac - ao
    wchg = hchg if wih else achg
    lchg = achg if wih else hchg

    if lchg > wchg:
        expected = 1
    elif lchg < wchg:
        expected = 0
    else:
        expected = None  # 동률 → NaN이 맞음

    if expected is None:
        if pd.isna(wd):
            v3_ok += 1
        else:
            print(f'  NG {label} 동률인데 winner_direction={wd} (NaN이어야 함)')
            v3_fail += 1
    elif pd.isna(wd):
        print(f'  NG {label} winner_direction=NaN (재계산={expected})')
        v3_fail += 1
    elif int(wd) != expected:
        print(f'  NG {label} winner_direction={int(wd)} != 재계산={expected}')
        v3_fail += 1
    else:
        v3_ok += 1

if v3_fail == 0:
    print(f'  OK {v3_ok}개 winner_direction 일치 (건너뜀: {v3_skip}개)')
else:
    print(f'  NG {v3_fail}개 불일치, {v3_ok}개 일치, {v3_skip}개 건너뜀')
ok_total += v3_ok; fail_total += v3_fail


# ──────────────────────────────────────────────────────────────────
# 요약
# ──────────────────────────────────────────────────────────────────
print()
print('=' * 60)
print('검증 요약')
print('=' * 60)
print(f'  정상: {ok_total}개')
print(f'  경고: {warn_total}개')
print(f'  오류: {fail_total}개')

if fail_total == 0 and warn_total == 0:
    print('\n  OK 모든 검증 통과')
elif fail_total == 0:
    print(f'\n  WARN 경고 {warn_total}개 확인 필요 (오류 없음)')
else:
    print(f'\n  NG 오류 {fail_total}개 수정 필요')
    print('  -> python validate_odds.py [날짜] --fix  로 winner_direction 재계산 가능')

# ──────────────────────────────────────────────────────────────────
# --fix: winner_direction을 open/close 기준으로 전체 재계산
# ──────────────────────────────────────────────────────────────────
if '--fix' in sys.argv:
    print()
    print('=' * 60)
    print('winner_direction 재계산 (전체 CSV)')
    print('=' * 60)
    df_all = pd.read_csv(CSV_PATH)
    fixed = 0
    for idx, row in df_all.iterrows():
        ho = row.get('home_open')
        hc = row.get('home_close')
        ao = row.get('away_open')
        ac = row.get('away_close')
        wih = row.get('winner_is_home')
        if pd.isna(ho) or pd.isna(hc) or pd.isna(ao) or pd.isna(ac) or pd.isna(wih):
            continue
        hchg = hc - ho
        achg = ac - ao
        wchg = hchg if wih else achg
        lchg = achg if wih else hchg
        if lchg > wchg:
            new_wd = 1
        elif lchg < wchg:
            new_wd = 0
        else:
            new_wd = float('nan')
        old_wd = row.get('winner_direction')
        changed = (pd.isna(old_wd) and pd.notna(new_wd)) or \
                  (pd.notna(old_wd) and pd.isna(new_wd)) or \
                  (pd.notna(old_wd) and pd.notna(new_wd) and int(old_wd) != int(new_wd))
        if changed:
            df_all.at[idx, 'winner_direction'] = new_wd if pd.notna(new_wd) else None
            fixed += 1
    df_all.to_csv(CSV_PATH, index=False, encoding='utf-8-sig')
    print(f'  {fixed}개 행 수정 완료 -> {CSV_PATH} 저장')

sys.exit(0 if fail_total == 0 else 1)
