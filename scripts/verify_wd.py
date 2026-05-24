import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np

df = pd.read_csv('kbo_odds.csv')
g = pd.read_csv('kbo_games.csv')

game_wih = g.set_index(['date', 'slot'])['winner_is_home'].to_dict()

total_ok = total_mm = total_skip = 0
mismatch_rows = []

for idx, r in df.iterrows():
    key = (r['date'], r['slot'])
    wih_raw = game_wih.get(key)
    if wih_raw is None or (isinstance(wih_raw, float) and np.isnan(wih_raw)):
        total_skip += 1
        continue
    ho = r['home_open']; hc = r['home_close']
    ao = r['away_open']; ac = r['away_close']
    wd_s = r['winner_direction']
    if pd.isna(wd_s) or any(pd.isna(v) for v in [ho, hc, ao, ac]):
        total_skip += 1
        continue
    hchg = float(hc) - float(ho)
    achg = float(ac) - float(ao)
    w_is_home = bool(wih_raw)
    wchg = hchg if w_is_home else achg
    lchg = achg if w_is_home else hchg
    if abs(wchg - lchg) < 0.001:
        total_skip += 1
        continue
    wd_c = 1.0 if wchg > lchg else 0.0
    if wd_s == wd_c:
        total_ok += 1
    else:
        total_mm += 1
        mismatch_rows.append({
            'date': r['date'], 'slot': int(r['slot']),
            'bookmaker': r['bookmaker'],
            'stored': wd_s, 'calc': wd_c,
            'wchg': round(wchg, 4), 'lchg': round(lchg, 4)
        })

print(f'=== 전체 검증 결과 ===')
print(f'OK={total_ok}  MISMATCH={total_mm}  SKIP={total_skip}')
print(f'MISMATCH 비율: {total_mm/(total_ok+total_mm)*100:.2f}%' if (total_ok+total_mm) > 0 else '')

if mismatch_rows:
    print(f'\n불일치 샘플 (최대 20개):')
    for r in mismatch_rows[:20]:
        print(f"  {r['date']} slot{r['slot']} {r['bookmaker']}: stored={r['stored']} calc={r['calc']} wchg={r['wchg']} lchg={r['lchg']}")
else:
    print('\n불일치 없음 - 전체 일치')

# 날짜별 집계
print('\n=== 날짜별 집계 ===')
date_stats = {}
for idx, r in df.iterrows():
    key = (r['date'], r['slot'])
    wih_raw = game_wih.get(key)
    if wih_raw is None or (isinstance(wih_raw, float) and np.isnan(wih_raw)):
        continue
    ho = r['home_open']; hc = r['home_close']
    ao = r['away_open']; ac = r['away_close']
    wd_s = r['winner_direction']
    if pd.isna(wd_s) or any(pd.isna(v) for v in [ho, hc, ao, ac]):
        continue
    hchg = float(hc) - float(ho)
    achg = float(ac) - float(ao)
    w_is_home = bool(wih_raw)
    wchg = hchg if w_is_home else achg
    lchg = achg if w_is_home else hchg
    if abs(wchg - lchg) < 0.001:
        continue
    wd_c = 1.0 if wchg > lchg else 0.0
    date = r['date']
    if date not in date_stats:
        date_stats[date] = [0, 0]
    if wd_s == wd_c:
        date_stats[date][0] += 1
    else:
        date_stats[date][1] += 1

for date in sorted(date_stats):
    ok, mm = date_stats[date]
    flag = ' *** MISMATCH ***' if mm > 0 else ''
    print(f'  {date}: OK={ok} MISMATCH={mm}{flag}')
