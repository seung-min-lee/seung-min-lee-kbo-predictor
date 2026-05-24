import sys; sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd, numpy as np

df = pd.read_csv('kbo_odds.csv')
g = pd.read_csv('kbo_games.csv')
print(f'총 {len(df)}행 로드')

def calc_wd(ho, hc, ao, ac, wih):
    """WD=1: 승리팀 배당변동 > 패배팀 배당변동"""
    try:
        if any(v is None or (isinstance(v, float) and np.isnan(v)) for v in [ho, hc, ao, ac]):
            return np.nan
        hchg = float(hc) - float(ho)
        achg = float(ac) - float(ao)
        wchg = hchg if wih else achg
        lchg = achg if wih else hchg
        if abs(wchg - lchg) < 0.001:
            return np.nan
        return 1.0 if wchg > lchg else 0.0
    except:
        return np.nan

# kbo_games.csv에서 (date, slot) → winner_is_home 참조
game_wih = g.set_index(['date', 'slot'])['winner_is_home'].to_dict()

updated = skipped = 0
for idx, r in df.iterrows():
    key = (r['date'], r['slot'])
    wih_raw = game_wih.get(key)
    if wih_raw is None or (isinstance(wih_raw, float) and np.isnan(wih_raw)):
        skipped += 1
        continue
    ho = r['home_open']; hc = r['home_close']
    ao = r['away_open']; ac = r['away_close']
    if any(pd.isna(v) for v in [ho, hc, ao, ac]):
        skipped += 1
        continue
    df.at[idx, 'winner_direction'] = calc_wd(ho, hc, ao, ac, bool(wih_raw))
    updated += 1

df.to_csv('kbo_odds.csv', index=False)
print(f'재계산 완료: {updated}행 업데이트, {skipped}행 스킵')

# 날짜별 샘플 검증
print('\n=== 날짜별 샘플 (슬롯1) ===')
for date in sorted(df['date'].unique())[-10:]:
    d_df = df[(df['date'] == date) & (df['slot'] == 1)]
    d_g = g[(g['date'] == date) & (g['slot'] == 1.0)]
    if d_df.empty or d_g.empty:
        continue
    wih = d_g['winner_is_home'].iloc[0]
    if pd.isna(wih):
        continue
    w_is_home = bool(wih)
    ok = mm = 0
    for _, row in d_df.iterrows():
        ho2 = row['home_open']; hc2 = row['home_close']
        ao2 = row['away_open']; ac2 = row['away_close']
        wd_s = row['winner_direction']
        if pd.isna(wd_s) or any(pd.isna(v) for v in [ho2, hc2, ao2, ac2]):
            continue
        hchg = hc2 - ho2; achg = ac2 - ao2
        wchg = hchg if w_is_home else achg
        lchg = achg if w_is_home else hchg
        if abs(wchg - lchg) < 0.001:
            continue
        wd_c = 1.0 if wchg > lchg else 0.0
        if wd_s == wd_c: ok += 1
        else: mm += 1
    total = ok + mm
    if total == 0:
        continue
    print(f'  {date}: OK={ok} MISMATCH={mm}')
