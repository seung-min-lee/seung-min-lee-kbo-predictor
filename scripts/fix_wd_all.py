"""
kbo_odds.csv 전체 winner_direction 재계산
올바른 공식: WD=1 if lchg > wchg (배당↓팀이김=마켓정배)
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np

df = pd.read_csv('kbo_odds.csv')
print(f'총 {len(df)}행 로드')

def calc_wd(ho, hc, ao, ac, wih):
    """
    WD=1: 승리팀 배당 상승 (배당↑팀이김, 이변)
    WD=0: 승리팀 배당 하락 (배당↓팀이김, 정배)
    """
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [ho, hc, ao, ac]):
            return np.nan
        wchg = float(hc) - float(ho) if wih else float(ac) - float(ao)
        if abs(wchg) < 0.001:
            return np.nan
        return 1.0 if wchg > 0 else 0.0
    except:
        return np.nan

updated = 0
skipped = 0

for idx, r in df.iterrows():
    ho = r['home_open']; hc = r['home_close']
    ao = r['away_open']; ac = r['away_close']
    wih = r['winner_is_home']

    if pd.isna(wih):
        skipped += 1
        continue
    if any(pd.isna(v) for v in [ho, hc, ao, ac]):
        skipped += 1
        continue

    wd_new = calc_wd(ho, hc, ao, ac, bool(wih))
    df.at[idx, 'winner_direction'] = wd_new
    updated += 1

df.to_csv('kbo_odds.csv', index=False)
print(f'재계산 완료: {updated}행 업데이트, {skipped}행 스킵')

# 검증
print('\n=== 날짜별 샘플 검증 ===')
g = pd.read_csv('kbo_games.csv')
for date in ['2026-05-06', '2026-05-19', '2026-05-21', '2026-05-22']:
    d_df = df[df['date'] == date]
    d_g = g[g['date'] == date][['slot', 'winner_is_home']]
    mm = ok = 0
    for _, grow in d_g.iterrows():
        slot = grow['slot']
        wih = grow['winner_is_home']
        if pd.isna(wih): continue
        s = d_df[d_df['slot'] == slot]
        for _, row in s.iterrows():
            ho2 = row['home_open']; hc2 = row['home_close']
            ao2 = row['away_open']; ac2 = row['away_close']
            wd_s = row['winner_direction']
            if pd.isna(wd_s): continue
            if any(pd.isna(v) for v in [ho2, hc2, ao2, ac2]): continue
            wchg = (hc2 - ho2) if wih else (ac2 - ao2)
            if abs(wchg) < 0.001:
                continue
            wd_c = 1.0 if wchg > 0 else 0.0
            if wd_s == wd_c:
                ok += 1
            else:
                mm += 1
    total = ok + mm
    print(f'  {date}: OK={ok} MISMATCH={mm} ({mm/total*100:.0f}% 불일치)' if total > 0 else f'  {date}: 데이터 없음')
