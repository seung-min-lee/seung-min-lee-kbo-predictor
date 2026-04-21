import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import LeaveOneOut
from sklearn.metrics import accuracy_score
import json, warnings
warnings.filterwarnings('ignore')

CSV_PATH   = 'kbo_odds.csv'
PRED_PATH  = 'kbo_predictions.json'
BOOKMAKERS = ['10x10bet','1xBet','22Bet','Alphabet','BetInAsia','Bets.io',
              'Cloudbet','GambleCity','Kobet','Melbet','Momobet','Roobet',
              'Stake.com','VOBET','bwin']
WINDOW = 3

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

def analyze_bookmaker_patterns(df, slot):
    slot_df = df[df['slot']==slot]
    dates = sorted(slot_df['date_order'].unique())
    if len(dates) < 4: return None
    bk_patterns = {}
    for bk in BOOKMAKERS:
        bk_df = slot_df[slot_df['bookmaker']==bk].sort_values('date_order')
        if len(bk_df) < 4: continue
        seq = bk_df['direction'].tolist()
        analysis = analyze_pattern(seq)
        bk_patterns[bk] = {'seq': seq, 'analysis': analysis}
    return bk_patterns

def vote_prediction(bk_patterns):
    votes = {0: 0.0, 1: 0.0}
    pass_count = 0; total = 0
    for bk, data in bk_patterns.items():
        a = data['analysis']
        if a.get('pass') or a['rec'] is None:
            pass_count += 1; continue
        votes[a['rec']] += a['score']
        total += 1
    if total == 0 or pass_count > total:
        return None, 0, '패스 권장 (불규칙/교대 다수)'
    winner = max(votes, key=votes.get)
    total_score = votes[0] + votes[1]
    confidence = votes[winner] / total_score if total_score > 0 else 0
    reason = f"투표: 1={votes[1]:.2f} vs 0={votes[0]:.2f}"
    return winner, confidence, reason

# ── 데이터 로드 ───────────────────────────────────────
print('데이터 로드 중...')
df = pd.read_csv(CSV_PATH)
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)
df = df.sort_values(['slot','bookmaker','date_order']).reset_index(drop=True)
print(f'데이터 로드: {len(df)}행 | {len(date_map)}일치 | slot: {sorted(df["slot"].unique())}')

# ── ML 보조 모델 ──────────────────────────────────────
def make_feat(df, slot, window_dates):
    slot_df = df[df['slot']==slot]
    feat = []
    for d in window_dates:
        day_df = slot_df[slot_df['date_order']==d]
        for bk in BOOKMAKERS:
            r = day_df[day_df['bookmaker']==bk]
            feat.append(int(r['direction'].values[0]) if len(r)>0 else -1)
    return feat

X_list, y_list = [], []
for slot in range(1, 6):
    slot_df = df[df['slot']==slot]
    dates = sorted(slot_df['date_order'].unique())
    if len(dates) < WINDOW+1: continue
    for i in range(len(dates)-WINDOW):
        feat = make_feat(df, slot, dates[i:i+WINDOW])
        t_df = slot_df[slot_df['date_order']==dates[i+WINDOW]]
        if len(t_df)==0: continue
        t = t_df.iloc[0]
        X_list.append(feat)
        y_list.append(1 if t['winner']==t['home'] else 0)

X, y = np.array(X_list), np.array(y_list)
print(f'ML 학습 샘플: {len(X)}개')

preds_loo = []
for tr, te in LeaveOneOut().split(X):
    m = RandomForestClassifier(n_estimators=200, random_state=42)
    m.fit(X[tr], y[tr])
    preds_loo.append(m.predict(X[te])[0])
ml_acc = accuracy_score(y, preds_loo)
print(f'ML 보조 정확도: {ml_acc:.1%} ({int(ml_acc*len(y))}/{len(y)})')

model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X, y)

# ── 슬롯별 패턴 분석 + 예측 ──────────────────────────
print('\n' + '='*60)
print('패턴 분석 및 예측')
print('='*60)

predictions = {}

for slot in range(1, 6):
    slot_df = df[df['slot']==slot]
    dates = sorted(slot_df['date_order'].unique())
    if len(dates) < 4:
        print(f'\n[SLOT {slot}] 데이터 부족')
        continue

    last = slot_df[slot_df['date_order']==dates[-1]].iloc[0]
    print(f'\n[SLOT {slot}] 최근: {last["home"]} vs {last["away"]} ({last["date"]})')
    print('-'*55)

    bk_patterns = analyze_bookmaker_patterns(df, slot)
    if not bk_patterns: continue

    consensus_seq = []
    for di in dates:
        slot_day = slot_df[slot_df['date_order']==di]
        vals = []
        for bk in BOOKMAKERS:
            r = slot_day[slot_day['bookmaker']==bk]
            if len(r) > 0: vals.append(int(r['direction'].values[0]))
        if vals:
            consensus_seq.append(1 if sum(vals) > len(vals)/2 else 0)

    print(f'  합산 패턴: [{" ".join(str(x) for x in consensus_seq)}]')
    segs = segment_patterns(consensus_seq)
    if segs:
        print(f'  분할 패턴:')
        for desc, _, rec in segs[:3]:
            rec_str = f'→ 추천: {rec}' if rec is not None else ''
            print(f'    {desc} {rec_str}')

    key_bks = ['BetInAsia','1xBet','Alphabet','bwin','Stake.com']
    print()
    for bk in key_bks:
        if bk not in bk_patterns: continue
        data = bk_patterns[bk]
        seq_str = ''.join(str(x) for x in data['seq'])
        a = data['analysis']
        pass_mark = ' [패스]' if a.get('pass') else ''
        rec_str = f"→ 추천: {a['rec']}" if a['rec'] is not None else '→ 추천없음'
        print(f"  {bk:12s}: [{seq_str}] {a['desc']}{pass_mark} {rec_str}")
        if a.get('segments') and a['type'] in ('분할패턴','불규칙'):
            print(f"  {'':12s}  분할: {a['segments'][0]}")

    final_rec, confidence, reason = vote_prediction(bk_patterns)

    if len(dates) >= WINDOW:
        feat = make_feat(df, slot, dates[-WINDOW:])
        X_pred = np.array(feat).reshape(1,-1)
        ml_pred = model.predict(X_pred)[0]
        ml_proba = model.predict_proba(X_pred)[0]
    else:
        ml_pred, ml_proba = None, [0.5, 0.5]

    print(f'\n  패턴 투표: {reason}')
    if ml_pred is not None:
        print(f'  ML 보조:   홈승={ml_proba[1]:.1%} | 원정승={ml_proba[0]:.1%}')

    if final_rec is None:
        print(f'  최종 추천: 패스')
        rec_str = 'PASS'
    else:
        winner_str = 'HOME(1)' if final_rec==1 else 'AWAY(0)'
        print(f'  최종 추천: {winner_str} 승리 (신뢰도 {confidence:.1%})')
        rec_str = winner_str

    predictions[f'slot_{slot}'] = {
        'slot': slot,
        'last_home': last['home'],
        'last_away': last['away'],
        'consensus_seq': consensus_seq,
        'recommendation': rec_str,
        'confidence': round(confidence, 3),
        'ml_home_prob': round(float(ml_proba[1]), 3),
        'ml_away_prob': round(float(ml_proba[0]), 3),
        'verified': False,
        'actual': None,
    }

with open(PRED_PATH, 'w', encoding='utf-8') as f:
    json.dump(predictions, f, ensure_ascii=False, indent=2)
print(f'\n예측 저장 완료: {PRED_PATH}')