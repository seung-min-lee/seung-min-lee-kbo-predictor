import os, sys

# Anaconda 환경에서 구버전 sklearn 충돌 방지: 로컬 .deps 우선 로드
_deps = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.deps')
if os.path.isdir(_deps) and _deps not in sys.path:
    sys.path.insert(0, _deps)

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import accuracy_score
from datetime import datetime, timedelta
import json, warnings
warnings.filterwarnings('ignore')

CSV_PATH   = 'kbo_odds.csv'
GAMES_PATH = 'kbo_games.csv'
PRED_PATH  = 'kbo_predictions.json'
WINDOW = 10   # 팀별 최근 N경기 참조

# ── 패턴 분석 함수 (변경 없음) ─────────────────────────────
def find_runs(seq):
    runs = []
    cur, cnt = seq[0], 1
    for v in seq[1:]:
        if v == cur: cnt += 1
        else: runs.append((cur, cnt)); cur = v; cnt = 1
    runs.append((cur, cnt))
    return runs

def check_mirror(seq):
    n = len(seq)
    for h in range(1, n//2+1):
        if n < h*2: break
        front = seq[-h*2:-h]
        back  = seq[-h:]
        if list(back) == [1-x for x in front]:
            return h, front, back
    return None

def check_repeat_block(seq):
    n = len(seq)
    for bl in range(1, n//2+1):
        chunk = seq[:bl]
        if all(seq[i] == chunk[i % bl] for i in range(n)):
            return bl, chunk
    return None

def check_palindrome(seq):
    return list(seq) == list(reversed(seq))

def check_alternating(seq):
    return len(seq) >= 2 and all(seq[i] != seq[i+1] for i in range(len(seq)-1))

def check_block_split(seq):
    n = len(seq)
    for sp in range(1, n):
        f, b = seq[:sp], seq[sp:]
        if len(set(f))==1 and len(set(b))==1 and f[0]!=b[0]:
            return sp, f[0], b[0]
    return None

def check_fold_mirror(seq):
    n = len(seq)
    results = []
    for sp in range(2, n-1):
        for length in range(2, sp+1):
            front = seq[sp-length:sp]
            back  = seq[sp:sp+length]
            if len(back) < length: continue
            if list(back) == [1-x for x in front]:
                tail = seq[sp+length:]
                results.append((sp-length, sp, sp+length, front, back, tail))
    return results

def check_inner_palindrome(seq):
    n = len(seq)
    results = []
    for start in range(n):
        for end in range(start+2, n+1):
            chunk = seq[start:end]
            if len(chunk) >= 2 and list(chunk) == list(reversed(chunk)):
                prefix = seq[:start]
                suffix = seq[end:]
                results.append((start, end, chunk, prefix, suffix))
    results.sort(key=lambda x: -(x[1]-x[0]))
    return results

def check_run_shape(seq):
    runs = find_runs(seq)
    lens = [r[1] for r in runs]
    if len(lens) < 2: return None
    asc   = lens == sorted(lens)
    desc  = lens == sorted(lens, reverse=True)
    peak  = lens.index(max(lens))
    mountain = (lens[:peak+1] == sorted(lens[:peak+1]) and
                lens[peak:] == sorted(lens[peak:], reverse=True) and
                0 < peak < len(lens)-1)
    vi = lens.index(min(lens))
    valley = (lens[:vi+1] == sorted(lens[:vi+1], reverse=True) and
              lens[vi:] == sorted(lens[vi:]) and
              0 < vi < len(lens)-1)
    if asc:      return 'asc', lens
    if desc:     return 'desc', lens
    if mountain: return 'mountain', lens
    if valley:   return 'valley', lens
    return None

def tail_recommendation(tail):
    if not tail: return None, None
    s = ''.join(str(x) for x in tail)
    if check_alternating(tail) and len(tail) >= 2:
        return 1-tail[-1], f'꼬리[{s}]=10101→{1-tail[-1]}'
    mir = check_mirror(tail)
    if mir:
        h, front, back = mir
        rec = 1 - tail[-h*2] if len(tail) > h*2 else 1-tail[0]
        return rec, f'꼬리[{s}]=Mirror→{rec}'
    rb = check_repeat_block(tail)
    if rb:
        bl, chunk = rb
        rec = chunk[len(tail) % bl]
        return rec, f'꼬리[{s}]=반복→{rec}'
    bs = check_block_split(tail)
    if bs:
        _, f_val, _ = bs
        return f_val, f'꼬리[{s}]=연속블록→{f_val}'
    for run_len in range(2, len(tail)+1):
        if len(set(tail[-run_len:])) == 1:
            val = tail[-1]
            return 1-val, f'꼬리[{s}]=끝{run_len}연속{val}→{1-val}'
    return None, f'꼬리[{s}]=불규칙'

def label_part(part):
    s = ''.join(str(x) for x in part)
    rb  = check_repeat_block(part)
    bs  = check_block_split(part)
    alt = check_alternating(part)
    pal = check_palindrome(part)
    mir = check_mirror(part)
    if rb:    return f'[{s}]=반복[{"".join(str(x) for x in rb[1])}]×{len(part)//rb[0]}', 'rep', rb
    elif bs:  return f'[{s}]=연속블록', 'blk', bs
    elif alt: return f'[{s}]=10101', 'alt', None
    elif pal: return f'[{s}]=대칭', 'pal', None
    elif mir: return f'[{s}]=Mirror', 'mir', mir
    else:     return f'[{s}]', None, None

def next_from_last(part, kind, info):
    if kind == 'rep':
        bl, chunk = info
        return chunk[len(part) % bl]
    elif kind == 'blk':
        _, f_val, _ = info
        return f_val
    elif kind == 'alt':
        return 1 - part[-1]
    elif kind == 'pal':
        return 1 - part[-1]
    elif kind == 'mir':
        return 1 - part[0]
    return None

def segment_patterns(seq):
    n = len(seq)
    found = []
    for i in range(2, n-1):
        parts = [seq[:i], seq[i:]]
        labeled = [label_part(p) for p in parts]
        named = sum(1 for _,k,_ in labeled if k is not None)
        if named >= 1:
            desc = ' + '.join(l for l,_,_ in labeled)
            _, last_kind, last_info = labeled[-1]
            rec = next_from_last(parts[-1], last_kind, last_info)
            found.append((desc, parts[-1], rec))
    for i in range(2, n-3):
        for j in range(i+2, n-1):
            parts = [seq[:i], seq[i:j], seq[j:]]
            labeled = [label_part(p) for p in parts]
            named = sum(1 for _,k,_ in labeled if k is not None)
            if named >= 2:
                desc = ' + '.join(l for l,_,_ in labeled)
                _, last_kind, last_info = labeled[-1]
                rec = next_from_last(parts[-1], last_kind, last_info)
                found.append((desc, parts[-1], rec))
    found.sort(key=lambda x: -x[0].count('='))
    return found[:5]

def analyze_pattern(seq):
    n = len(seq)
    s = ''.join(str(x) for x in seq)
    candidates = []

    if len(set(seq)) == 1:
        candidates.append({'type':'전체연속',
                           'desc':f'[{s}] {seq[0]}이 {n}번 연속',
                           'rec': 1-seq[0], 'score': 0.70})

    if check_alternating(seq) and n >= 3:
        candidates.append({'type':'10101',
                           'desc':f'[{s}] 교대 패턴',
                           'rec': 1-seq[-1], 'score': 0.50, 'pass': True})

    mir = check_mirror(seq)
    if mir:
        h, front, back = mir
        next_val = 1 - seq[-h*2] if len(seq) > h*2 else 1-seq[0]
        candidates.append({'type':'Mirror',
                           'desc':f'[{s}] Mirror [{s[-h*2:-h]}|{s[-h:]}]',
                           'rec': next_val, 'score': 0.85})

    rb = check_repeat_block(seq)
    if rb:
        bl, chunk = rb
        next_val = chunk[len(seq) % bl]
        candidates.append({'type':'반복블록',
                           'desc':f'[{s}] [{"".join(str(x) for x in chunk)}]×{n//bl} 반복',
                           'rec': next_val, 'score': 0.80})

    if check_palindrome(seq) and n > 2:
        candidates.append({'type':'대칭',
                           'desc':f'[{s}] 좌우 대칭',
                           'rec': None, 'score': 0.60})

    bs = check_block_split(seq)
    if bs:
        sp, f_val, b_val = bs
        f_len, b_len = sp, n-sp
        if f_len == b_len:
            candidates.append({'type':'연속블록대칭',
                               'desc':f'[{s}] {f_val}×{f_len}|{b_val}×{b_len}',
                               'rec': f_val, 'score': 0.82})
        else:
            candidates.append({'type':'연속블록',
                               'desc':f'[{s}] {f_val}×{f_len}|{b_val}×{b_len}',
                               'rec': b_val, 'score': 0.72})

    shape = check_run_shape(seq)
    if shape:
        kind, lens = shape
        runs = find_runs(seq)
        desc_map = {'asc':'증가런','desc':'감소런','mountain':'산형','valley':'골형'}
        candidates.append({'type': desc_map.get(kind,'런'),
                           'desc':f'[{s}] {desc_map.get(kind,"")} 런={lens}',
                           'rec': runs[-1][0], 'score': 0.65})

    for run_len in range(2, min(n, 6)+1):
        if len(set(seq[-run_len:])) == 1:
            val = seq[-1]
            candidates.append({'type':'끝연속',
                               'desc':f'[{s}] 끝 {run_len}개 연속 {val}',
                               'rec': 1-val, 'score': 0.58+run_len*0.04})
            break

    fold_results = check_fold_mirror(seq)
    for (start, sp, end, front, back, tail) in fold_results:
        front_s = ''.join(str(x) for x in front)
        back_s  = ''.join(str(x) for x in back)
        tail_rec, tail_desc = tail_recommendation(list(tail))
        if tail_rec is not None:
            candidates.append({'type':'반접기+꼬리',
                               'desc':f'[{s}] 반접기[{front_s}|{back_s}] + {tail_desc}',
                               'rec': tail_rec, 'score': 0.78})
            break

    inner_pals = check_inner_palindrome(seq)
    for (start, end, chunk, prefix, suffix) in inner_pals:
        chunk_s = ''.join(str(x) for x in chunk)
        if len(chunk) < 2: continue
        tail_rec, tail_desc = tail_recommendation(list(suffix))
        if tail_rec is not None:
            candidates.append({'type':'중간대칭+꼬리',
                               'desc':f'[{s}] 중간대칭[{chunk_s}] + {tail_desc}',
                               'rec': tail_rec, 'score': 0.75})
            break
        elif not suffix:
            rec = 1 - chunk[-1]
            candidates.append({'type':'중간대칭',
                               'desc':f'[{s}] 중간대칭[{chunk_s}]→다음{rec}',
                               'rec': rec, 'score': 0.72})
            break

    segs = segment_patterns(seq)

    if not candidates:
        seg_rec = None
        seg_desc = None
        for desc, last_part, rec in segs:
            if rec is not None:
                seg_rec = rec; seg_desc = desc; break
        if seg_rec is not None:
            return {'type':'분할패턴',
                    'desc':f'[{s}] 분할: {seg_desc}',
                    'rec': seg_rec, 'score': 0.70, 'pass': False,
                    'segments': [d for d,_,_ in segs]}
        return {'type':'불규칙',
                'desc':f'[{s}] 불규칙 → 패스',
                'rec': None, 'score': 0.0, 'pass': True,
                'segments': [d for d,_,_ in segs]}

    best = max(candidates, key=lambda x: x['score'])
    best.setdefault('pass', False)
    best['segments'] = [d for d,_,_ in segs]
    if best['type'] == '10101':
        best['pass'] = True
    return best


# ── 데이터 로드 ───────────────────────────────────────────
print('데이터 로드 중...')
df = pd.read_csv(CSV_PATH)
df['direction'] = df['consensus'].map({'home': 1, 'away': 0})
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)
df = df.sort_values(['date_order', 'slot', 'bookmaker']).reset_index(drop=True)

# 경기 단위 집계
game_df = df.drop_duplicates('match_id')[[
    'match_id', 'date', 'date_order', 'slot',
    'home', 'away', 'winner', 'winner_is_home', 'consensus'
]].copy().sort_values('date_order').reset_index(drop=True)
game_df['consensus_win'] = (
    ((game_df['consensus'] == 'home') & game_df['winner_is_home']) |
    ((game_df['consensus'] == 'away') & ~game_df['winner_is_home'])
).astype(int)

print(f'데이터 로드: {len(df)}행 | {len(date_map)}일치 | {len(game_df)}경기')


# ── 팀 기반 시퀀스 함수 ───────────────────────────────────
def get_team_triple_seq(team, before_date_order, window=WINDOW):
    """팀 최근 경기 3개 이진 시퀀스 반환:
    - direction : 팀이 정배(1) or 역배(0)
    - fav_win   : 정배팀 승(1) or 역배팀 승(0)
    - team_win  : 해당 팀 승(1) or 패(0)
    """
    mask = (
        ((game_df['home'] == team) | (game_df['away'] == team)) &
        (game_df['date_order'] < before_date_order)
    )
    recent = game_df[mask].sort_values('date_order').tail(window)
    direction_seq, fav_win_seq, team_win_seq = [], [], []
    for _, r in recent.iterrows():
        is_fav = (
            (r['consensus'] == 'home' and r['home'] == team) or
            (r['consensus'] == 'away' and r['away'] == team)
        )
        direction_seq.append(1 if is_fav else 0)
        fav_win_seq.append(int(r['consensus_win']))
        team_win_seq.append(1 if r['winner'] == team else 0)
    return direction_seq, fav_win_seq, team_win_seq

def get_team_win_seq(team, before_date_order, window=WINDOW):
    _, _, team_win = get_team_triple_seq(team, before_date_order, window)
    return team_win

def get_team_fav_seq(team, before_date_order, window=WINDOW):
    direction, _, _ = get_team_triple_seq(team, before_date_order, window)
    return direction

def make_feat_team(home, away, before_date_order):
    """홈팀 + 원정팀의 최근 승패/정배 시퀀스 피처 벡터 (4 × WINDOW)"""
    def pad(seq):
        return [-1] * (WINDOW - len(seq)) + seq

    hw = get_team_win_seq(home, before_date_order)
    aw = get_team_win_seq(away, before_date_order)
    hf = get_team_fav_seq(home, before_date_order)
    af = get_team_fav_seq(away, before_date_order)
    return pad(hw) + pad(aw) + pad(hf) + pad(af)

def seq_str(seq):
    return ''.join(str(x) for x in seq) if seq else '-'

def pat_rec(seq):
    """시퀀스 패턴 분석 → (추천값 or None, 설명문자열)"""
    if len(seq) < 3:
        return None, '데이터 부족'
    pa = analyze_pattern(seq)
    rec = pa['rec'] if not pa.get('pass') else None
    return rec, pa['desc']


# ── ML 모델 학습 ──────────────────────────────────────────
print('ML 모델 학습 중...')
X_list, y_list = [], []
for _, g in game_df.sort_values('date_order').iterrows():
    feat = make_feat_team(g['home'], g['away'], g['date_order'])
    if feat.count(-1) > WINDOW * 3:  # 데이터 부족 시 스킵
        continue
    X_list.append(feat)
    y_list.append(int(g['winner_is_home']))

X, y = np.array(X_list), np.array(y_list)
print(f'ML 학습 샘플: {len(X)}개')

if len(X) >= 10:
    preds_loo = []
    for tr, te in LeaveOneOut().split(X):
        m = RandomForestClassifier(n_estimators=200, random_state=42)
        m.fit(X[tr], y[tr])
        preds_loo.append(m.predict(X[te])[0])
    ml_acc = accuracy_score(y, preds_loo)
    print(f'ML 정확도(LOO): {ml_acc:.1%} ({int(ml_acc*len(y))}/{len(y)})')
else:
    ml_acc = 0.5
    print('ML 샘플 부족 → 스킵')

model = RandomForestClassifier(n_estimators=200, random_state=42)
if len(X) >= 2:
    model.fit(X, y)


# ── 다음 경기 탐색 ─────────────────────────────────────────
def parse_odds_date(raw):
    """Oddsportal 날짜 문자열 → datetime (실패시 None)"""
    today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
    s = str(raw).strip()
    if s.startswith('Today'):
        return today
    if s.startswith('Yesterday'):
        return today - timedelta(days=1)
    s = s.split(' - ')[0].strip()  # "14 Mar 2026 - Pre-season" → "14 Mar 2026"
    for fmt in ('%d %b %Y', '%Y-%m-%d', '%d %b'):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == '%d %b':
                dt = dt.replace(year=today.year)
            return dt
        except:
            continue
    return None

def get_latest_odds_date():
    """kbo_odds.csv 전체 날짜 파싱 후 최대값 반환"""
    parsed = [parse_odds_date(d) for d in df['date'].unique()]
    parsed = [d for d in parsed if d is not None]
    return max(parsed) if parsed else None

def find_upcoming_games():
    """kbo_games.csv에서 최신 odds 날짜 이후 첫 번째 경기일 탐색"""
    if not os.path.exists(GAMES_PATH):
        return [], None

    gdf = pd.read_csv(GAMES_PATH)
    latest_dt = get_latest_odds_date()
    if latest_dt is None:
        return [], None

    # 내일부터 7일 내 최초 경기일 탐색
    for delta in range(1, 8):
        target = (latest_dt + timedelta(days=delta)).strftime('%Y-%m-%d')
        day_games = gdf[gdf['date'] == target]
        if len(day_games) > 0:
            return day_games.to_dict('records'), target

    return [], None

upcoming_games, pred_date = find_upcoming_games()

# fallback: kbo_games.csv에 없으면 odds 마지막 날 경기들로 예측
if not upcoming_games:
    latest_date_order = game_df['date_order'].max()
    last_games = game_df[game_df['date_order'] == latest_date_order]
    upcoming_games = last_games.to_dict('records')
    pred_date = game_df[game_df['date_order'] == latest_date_order]['date'].iloc[0]
    print(f'kbo_games.csv 미탐색 → 마지막 기록 경기 재예측 ({pred_date})')
else:
    print(f'예측 대상 날짜: {pred_date} ({len(upcoming_games)}경기)')


# ── 경기별 예측 ───────────────────────────────────────────
print('\n' + '='*60)
print(f'패턴 분석 및 예측 ({pred_date})')
print('='*60)

max_date_order = game_df['date_order'].max() + 1  # 미래 date_order

predictions = {}

for i, game in enumerate(upcoming_games):
    home = game['home']
    away = game['away']
    slot = game.get('slot', i + 1)

    # 팀별 3개 시퀀스 수집
    h_dir, h_fav_win, h_team_win = get_team_triple_seq(home, max_date_order)
    a_dir, a_fav_win, a_team_win = get_team_triple_seq(away, max_date_order)

    # 패턴 분석 (각 팀 × 3 시퀀스)
    h_dir_rec,     h_dir_desc     = pat_rec(h_dir)
    h_fav_win_rec, h_fav_win_desc = pat_rec(h_fav_win)
    h_win_rec,     h_win_desc     = pat_rec(h_team_win)

    a_dir_rec,     a_dir_desc     = pat_rec(a_dir)
    a_fav_win_rec, a_fav_win_desc = pat_rec(a_fav_win)
    a_win_rec,     a_win_desc     = pat_rec(a_team_win)

    def fmt_rec(rec):
        if rec is None: return ' ?'
        return f' {rec}'

    print(f'\n{"="*62}')
    print(f'  {home}  vs  {away}')
    print(f'{"="*62}')
    print(f'  {"항목":<16} {"홈팀 "+home+" 시퀀스":^22}  {"원정팀 "+away+" 시퀀스":^22}')
    print(f'  {"-"*60}')

    # 1) 배당 변동 (정배=1, 역배=0)
    h_d = seq_str(h_dir);     a_d = seq_str(a_dir)
    print(f'  {"배당 변동":<16} [{h_d}] →{fmt_rec(h_dir_rec):<4}  [{a_d}] →{fmt_rec(a_dir_rec)}')
    print(f'  {"":16} {h_dir_desc}')
    print(f'  {"":16} {a_dir_desc}')

    # 2) 정배승(1) / 역배승(0)
    h_fw = seq_str(h_fav_win); a_fw = seq_str(a_fav_win)
    print(f'  {"정배승/역배승":<16} [{h_fw}] →{fmt_rec(h_fav_win_rec):<4}  [{a_fw}] →{fmt_rec(a_fav_win_rec)}')
    print(f'  {"":16} {h_fav_win_desc}')
    print(f'  {"":16} {a_fav_win_desc}')

    # 3) 팀 승(1) / 패(0)
    h_tw = seq_str(h_team_win); a_tw = seq_str(a_team_win)
    print(f'  {"팀 승패":<16} [{h_tw}] →{fmt_rec(h_win_rec):<4}  [{a_tw}] →{fmt_rec(a_win_rec)}')
    print(f'  {"":16} {h_win_desc}')
    print(f'  {"":16} {a_win_desc}')

    # 패턴 종합 추천 (팀 승패 기준: h_win_rec=1 → 홈팀 승, a_win_rec=1 → 원정팀 승)
    home_rec = h_win_rec
    away_rec = a_win_rec
    home_pa  = analyze_pattern(h_team_win) if len(h_team_win) >= 3 else None
    away_pa  = analyze_pattern(a_team_win) if len(a_team_win) >= 3 else None
    home_score = home_pa['score'] if home_pa else 0.5
    away_score = away_pa['score'] if away_pa else 0.5

    final_rec = None
    pattern_confidence = 0.0
    pattern_reason = ''

    if home_rec == 1 and away_rec == 0:
        final_rec = 1
        pattern_confidence = (home_score + away_score) / 2
        pattern_reason = f'홈 승 패턴({home_score:.0%}) + 원정 패 패턴({away_score:.0%})'
    elif home_rec == 0 and away_rec == 1:
        final_rec = 0
        pattern_confidence = (home_score + away_score) / 2
        pattern_reason = f'홈 패 패턴({home_score:.0%}) + 원정 승 패턴({away_score:.0%})'
    elif home_rec == 1 and away_rec is None:
        final_rec = 1
        pattern_confidence = home_score * 0.8
        pattern_reason = f'홈 승 패턴({home_score:.0%}) (원정 불규칙)'
    elif home_rec == 0 and away_rec is None:
        final_rec = 0
        pattern_confidence = home_score * 0.8
        pattern_reason = f'홈 패 패턴({home_score:.0%}) (원정 불규칙)'
    elif home_rec is None and away_rec == 1:
        final_rec = 0
        pattern_confidence = away_score * 0.8
        pattern_reason = f'원정 승 패턴({away_score:.0%}) (홈 불규칙)'
    elif home_rec is None and away_rec == 0:
        final_rec = 1
        pattern_confidence = away_score * 0.8
        pattern_reason = f'원정 패 패턴({away_score:.0%}) (홈 불규칙)'
    elif home_rec == 1 and away_rec == 1:
        pattern_reason = '팀승패 충돌 (둘 다 승 예측) → ML 판단'
    elif home_rec == 0 and away_rec == 0:
        pattern_reason = '팀승패 충돌 (둘 다 패 예측) → ML 판단'
    else:
        pattern_reason = '팀승패 불규칙 → ML 판단'

    # ML 보조
    feat = make_feat_team(home, away, max_date_order)
    X_pred = np.array(feat).reshape(1, -1)
    try:
        ml_proba = model.predict_proba(X_pred)[0]
    except:
        ml_proba = [0.5, 0.5]

    if final_rec is None:
        if ml_proba[1] >= 0.58:
            final_rec = 1
            pattern_confidence = float(ml_proba[1])
        elif ml_proba[0] >= 0.58:
            final_rec = 0
            pattern_confidence = float(ml_proba[0])

    print(f'  {"-"*60}')
    print(f'  패턴 판단: {pattern_reason}')
    print(f'  ML 보조:  홈승={ml_proba[1]:.1%} | 원정승={ml_proba[0]:.1%}')

    if final_rec is None:
        print(f'  최종 추천: PASS')
        rec_str = 'PASS'
    else:
        winner_str = f'HOME({home})' if final_rec == 1 else f'AWAY({away})'
        print(f'  최종 추천: {winner_str} 승리 (신뢰도 {pattern_confidence:.1%})')
        rec_str = 'HOME(1)' if final_rec == 1 else 'AWAY(0)'

    predictions[f'slot_{slot}'] = {
        'slot':            slot,
        'home':            home,
        'away':            away,
        'pred_date':       pred_date,
        # 홈팀 3 시퀀스
        'home_direction':  seq_str(h_dir),
        'home_fav_win':    seq_str(h_fav_win),
        'home_team_win':   seq_str(h_team_win),
        'home_dir_rec':    h_dir_rec,
        'home_fav_rec':    h_fav_win_rec,
        'home_win_rec':    h_win_rec,
        # 원정팀 3 시퀀스
        'away_direction':  seq_str(a_dir),
        'away_fav_win':    seq_str(a_fav_win),
        'away_team_win':   seq_str(a_team_win),
        'away_dir_rec':    a_dir_rec,
        'away_fav_rec':    a_fav_win_rec,
        'away_win_rec':    a_win_rec,
        'recommendation':  rec_str,
        'confidence':      round(pattern_confidence, 3),
        'ml_home_prob':    round(float(ml_proba[1]), 3),
        'ml_away_prob':    round(float(ml_proba[0]), 3),
        'verified':        False,
        'actual':          None,
    }

with open(PRED_PATH, 'w', encoding='utf-8') as f:
    json.dump(predictions, f, ensure_ascii=False, indent=2)
print(f'\n예측 저장 완료: {PRED_PATH}')
