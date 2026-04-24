import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

CSV_PATH = 'kbo_odds.csv'

df = pd.read_csv(CSV_PATH)
df['direction'] = df['consensus'].map({'home': 1, 'away': 0})
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)

# 경기 단위 집계 (match_id 기준)
game_df = df.drop_duplicates(subset='match_id')[
    ['match_id', 'date', 'date_order', 'slot', 'home', 'away',
     'winner', 'winner_is_home', 'consensus']
].copy()
game_df['direction'] = game_df['consensus'].map({'home': 1, 'away': 0})
game_df['consensus_win'] = (
    ((game_df['consensus'] == 'home') & game_df['winner_is_home']) |
    ((game_df['consensus'] == 'away') & ~game_df['winner_is_home'])
).astype(int)

print('=' * 60)
print('KBO 배당 백테스팅')
print('=' * 60)
print(f'전체 경기: {len(game_df)}경기 | 북메이커 행: {len(df)}행')
print(f'consensus 정확도 (전체): {game_df["consensus_win"].mean():.1%} ({game_df["consensus_win"].sum()}/{len(game_df)})')
print()


# ─────────────────────────────────────────────────────────
# ① 배당 변동성 블록 (Volatility Block)
# ─────────────────────────────────────────────────────────
print('=' * 60)
print('① 배당 변동성 블록 (Volatility Block)')
print('   정의: |home_change| 평균 >= 임계값 → volatile=1')
print('=' * 60)

vol_df = df[df['home_change'].notna()].copy()

def parse_change(val):
    try:
        return abs(float(str(val).replace('+', '')))
    except:
        return np.nan

vol_df['abs_change'] = vol_df['home_change'].apply(parse_change)

game_vol = (
    vol_df.groupby('match_id')['abs_change']
    .mean()
    .reset_index()
    .rename(columns={'abs_change': 'mean_abs_change'})
)
game_vol = game_vol.merge(game_df, on='match_id')

thresholds = [0.03, 0.05, 0.08, 0.10]
print(f'\n{"임계값":>8} {"고변동성":>8} {"저변동성":>8} {"고변동 consensus 승률":>20} {"저변동 consensus 승률":>20}')
print('-' * 70)
for thr in thresholds:
    high = game_vol[game_vol['mean_abs_change'] >= thr]
    low  = game_vol[game_vol['mean_abs_change'] < thr]
    if len(high) == 0 or len(low) == 0:
        continue
    print(f'{thr:>8.2f} {len(high):>8} {len(low):>8} '
          f'{high["consensus_win"].mean():>20.1%} '
          f'{low["consensus_win"].mean():>20.1%}')

# 변동성 사분위별 분석
game_vol['vol_quartile'] = pd.qcut(game_vol['mean_abs_change'], q=4,
                                    labels=['Q1(저)', 'Q2', 'Q3', 'Q4(고)'])
print('\n사분위별 consensus 승률:')
q_result = game_vol.groupby('vol_quartile', observed=True).agg(
    경기수=('consensus_win', 'count'),
    consensus_승률=('consensus_win', 'mean'),
    평균변동폭=('mean_abs_change', 'mean')
)
print(q_result.to_string())
print()


# ─────────────────────────────────────────────────────────
# ② 정/역배 교차 지속성 (Alternating Persistence)
# ─────────────────────────────────────────────────────────
print('=' * 60)
print('② 정/역배 교차 지속성 (Alternating Persistence)')
print('   정의: 101 또는 010 패턴 발생 후 다음 값이 교차(지속) or 반전')
print('=' * 60)

alt_results = []
for slot in sorted(df['slot'].unique()):
    slot_games = (
        game_df[game_df['slot'] == slot]
        .sort_values('date_order')
        .reset_index(drop=True)
    )
    if len(slot_games) < 4:
        continue

    seq = slot_games['direction'].tolist()
    home_seq = slot_games['winner_is_home'].astype(int).tolist()

    for i in range(len(seq) - 3):
        a, b, c = seq[i], seq[i+1], seq[i+2]
        nxt_dir = seq[i+3]
        nxt_win = home_seq[i+3]

        is_alt = (a != b and b != c)
        if not is_alt:
            continue

        continues_alt = int(c != nxt_dir)  # 1=교차 지속, 0=패턴 붕괴
        alt_results.append({
            'slot': slot,
            'pattern': f'{a}{b}{c}',
            'next_dir': nxt_dir,
            'continues_alt': continues_alt,
            'next_winner_is_home': nxt_win,
            'next_consensus': slot_games.iloc[i+3]['consensus'],
        })

alt_df = pd.DataFrame(alt_results)
if len(alt_df) > 0:
    total = len(alt_df)
    continues = alt_df['continues_alt'].sum()
    print(f'\n101/010 패턴 발생 후 분석 (총 {total}건):')
    print(f'  교차 지속 (alt 계속): {continues}건 ({continues/total:.1%})')
    print(f'  패턴 붕괴 (연속으로 전환): {total-continues}건 ({(total-continues)/total:.1%})')

    for pat in ['101', '010']:
        sub = alt_df[alt_df['pattern'] == pat]
        if len(sub) == 0:
            continue
        cont = sub['continues_alt'].mean()
        home_win = sub['next_winner_is_home'].mean()
        print(f'\n  [{pat}] 패턴 ({len(sub)}건):')
        print(f'    → 교차 지속률: {cont:.1%}')
        print(f'    → 다음 경기 홈 승률: {home_win:.1%}')
        print(f'    → 붕괴 후(연속 전환) 홈 승률: '
              f'{sub[sub["continues_alt"]==0]["next_winner_is_home"].mean():.1%}'
              if len(sub[sub["continues_alt"]==0]) > 0 else '    → 붕괴 사례 없음')
else:
    print('  해당 패턴 없음')
print()


# ─────────────────────────────────────────────────────────
# ③ 라인 무브먼트 역행 (Reverse Line Movement)
# ─────────────────────────────────────────────────────────
print('=' * 60)
print('③ 라인 무브먼트 역행 (RLM - Reverse Line Movement)')
print('   정의: home_direction=1 → 홈 배당 상승 (시장이 홈을 외면)')
print('   검증: consensus=home(홈 정배)이지만 홈 배당이 오른 경우 승률')
print('=' * 60)

rlm_df = df[df['home_direction'].notna()].copy()
rlm_df['home_direction'] = rlm_df['home_direction'].astype(int)

game_rlm = (
    rlm_df.groupby('match_id')
    .agg(
        rlm_ratio=('home_direction', 'mean'),  # 홈 배당 상승 북메이커 비율
        bk_count=('home_direction', 'count')
    )
    .reset_index()
    .merge(game_df, on='match_id')
)

# RLM 신호: consensus=home (홈이 정배)인데 다수 북메이커가 홈 배당을 올림
rlm_signal = game_rlm[game_rlm['consensus'] == 'home'].copy()
rlm_signal['rlm_flag'] = (rlm_signal['rlm_ratio'] > 0.5).astype(int)

if len(rlm_signal) > 0:
    for flag, label in [(1, 'RLM 발생 (정배인데 배당 상승)'), (0, 'RLM 없음 (정배+배당 하락)')]:
        sub = rlm_signal[rlm_signal['rlm_flag'] == flag]
        if len(sub) == 0:
            continue
        home_win = sub['winner_is_home'].mean()
        print(f'\n  {label} — {len(sub)}경기:')
        print(f'    홈팀 실제 승률: {home_win:.1%}')
        print(f'    시장 신뢰도: rlm_ratio 평균 = {sub["rlm_ratio"].mean():.2f}')

    # RLM 강도별 분석
    print('\n  RLM 강도별 홈 승률 (consensus=home 경기):')
    bins = [0, 0.3, 0.5, 0.7, 1.01]
    labels_b = ['0~30%(홈 지지)', '30~50%(중립)', '50~70%(약 RLM)', '70~100%(강 RLM)']
    rlm_signal['rlm_bin'] = pd.cut(rlm_signal['rlm_ratio'], bins=bins, labels=labels_b)
    rlm_bin_result = rlm_signal.groupby('rlm_bin', observed=True).agg(
        경기수=('winner_is_home', 'count'),
        홈_승률=('winner_is_home', 'mean')
    )
    print(rlm_bin_result.to_string())
else:
    print('  RLM 분석 대상 데이터 없음 (open 데이터 필요)')

print()


# ─────────────────────────────────────────────────────────
# 종합 요약
# ─────────────────────────────────────────────────────────
print('=' * 60)
print('종합 요약')
print('=' * 60)
print(f'  분석 기간: {df["date"].min()} ~ {df["date"].max()}')
print(f'  전체 경기: {len(game_df)}경기')
print(f'  consensus 전체 정확도: {game_df["consensus_win"].mean():.1%}')

if len(vol_df) > 0:
    best_q = q_result['consensus_승률'].idxmax()
    worst_q = q_result['consensus_승률'].idxmin()
    print(f'  ① 변동성: {best_q} 구간에서 consensus 승률 최고, {worst_q}에서 최저')

if len(alt_df) > 0:
    cont_rate = alt_df['continues_alt'].mean()
    print(f'  ② 교차 지속성: 101/010 후 교차 지속률 {cont_rate:.1%}')

if len(rlm_signal) > 0:
    rlm_home = rlm_signal[rlm_signal['rlm_flag']==1]['winner_is_home'].mean()
    no_rlm_home = rlm_signal[rlm_signal['rlm_flag']==0]['winner_is_home'].mean()
    if not np.isnan(rlm_home) and not np.isnan(no_rlm_home):
        print(f'  ③ RLM: 역행 시 홈 승률 {rlm_home:.1%} vs 정배 지지 시 {no_rlm_home:.1%}')
