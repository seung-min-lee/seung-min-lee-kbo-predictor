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
WINDOW     = 15   # 팀별 최근 N경기 참조
BM_SEQ_LEN = 17  # 슬롯별 북메이커 배당변동 시퀀스 길이

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

def check_run_mirror_pattern(seq):
    """런-길이 인코딩 기반 Mirror쌍 + 팰린드롬 패턴 분할 예측
    예: [0,0,1,1,0,0,0,1,0,0,0]
      runs: [(0,2),(1,2),(0,3),(1,1),(0,3)]
      → [00|11]=Mirror쌍 + [0001000]=팰린드롬(중심=1) → 다음=1
    반환: (예측값 or None, 설명 or None, 점수)
    """
    n = len(seq)
    if n < 4:
        return None, None, 0.0

    # Run-length encoding
    runs = []
    i = 0
    while i < n:
        j = i
        while j < n and seq[j] == seq[i]:
            j += 1
        runs.append((seq[i], j - i))
        i = j

    rn = len(runs)
    if rn < 2:
        return None, None, 0.0

    vals = [r[0] for r in runs]
    lens = [r[1] for r in runs]

    def runs_str(rs):
        return ''.join(''.join([str(r[0])] * r[1]) for r in rs)

    candidates = []

    # ── 1. 앞 K쌍이 Mirror → 나머지 구조 분석 ──────────────────
    for k in range(1, rn // 2 + 1):
        if 2 * k > rn:
            break
        head = runs[:k]
        next_k = runs[k:2 * k]

        is_mirror = all(
            head[i][0] != next_k[i][0] and head[i][1] == next_k[i][1]
            for i in range(k)
        )
        if not is_mirror:
            continue

        mirror_runs = runs[:2 * k]
        rest = runs[2 * k:]

        if not rest:
            # 전체 Mirror쌍 완성 → 새 사이클 첫 값
            nv = vals[0]
            candidates.append((
                nv,
                f'런분할 [{runs_str(mirror_runs)}]=Mirror완성 → 새사이클={nv}',
                0.80
            ))
            break

        rest_lens = [r[1] for r in rest]
        rest_vals = [r[0] for r in rest]
        rest_is_pal = rest_lens == rest_lens[::-1]

        if rest_is_pal:
            center = rest_vals[len(rest_vals) // 2]
            nv = center
            candidates.append((
                nv,
                (f'런분할 [{runs_str(mirror_runs)}]=Mirror'
                 f' + [{runs_str(rest)}]=팰린드롬(중심={center}) → 다음={nv}'),
                0.85
            ))
        else:
            # Mirror쌍 있고 나머지 비팰린드롬 → 나머지 끝값의 반대
            nv = 1 - rest_vals[-1]
            candidates.append((
                nv,
                (f'런분할 [{runs_str(mirror_runs)}]=Mirror'
                 f' + [{runs_str(rest)}] → 다음={nv}'),
                0.72
            ))

    # ── 2. 전체 또는 끝 구간이 팰린드롬 (Mirror쌍 없이) ───────────
    for start in range(rn - 1, -1, -1):
        sub_lens = lens[start:]
        if len(sub_lens) < 3:
            continue
        if sub_lens != sub_lens[::-1]:
            continue
        sub_vals = vals[start:]
        sub_runs = runs[start:]
        center = sub_vals[len(sub_vals) // 2]
        nv = center
        prefix = runs[:start]
        if start == 0:
            desc = f'런분할 [{runs_str(runs)}]=전체팰린드롬(중심={center}) → 다음={nv}'
        else:
            desc = (f'런분할 [{runs_str(prefix)}]'
                    f' + [{runs_str(sub_runs)}]=팰린드롬(중심={center}) → 다음={nv}')
        candidates.append((nv, desc, 0.78))
        break

    if not candidates:
        return None, None, 0.0

    best = max(candidates, key=lambda x: x[2])
    return best[0], best[1], best[2]

def check_staircase_pattern(seq):
    """런 길이가 등차수열(계단식)인 패턴 감지
    예: 111001 → runs [(1,3),(0,2),(1,1)] → 길이 [3,2,1] (Δ-1) → 다음 run=(0,0) 완성 → 새 사이클 시작=1
    예: 000110 → runs [(0,3),(1,2),(0,1)] → 길이 [3,2,1] (Δ-1) → 다음=0
    """
    runs = find_runs(seq)
    if len(runs) < 3:
        return None, None, 0.0
    lens = [r[1] for r in runs]
    diffs = [lens[i+1] - lens[i] for i in range(len(lens)-1)]
    if len(set(diffs)) != 1 or diffs[0] == 0:
        return None, None, 0.0
    step = diffs[0]
    next_len = lens[-1] + step
    s = ''.join(str(x) for x in seq)
    if next_len <= 0:
        # 계단 완성 → 새 사이클 시작값 = 첫 런 값
        nv = runs[0][0]
        return nv, f'계단식[{s}] 런={lens}(Δ{step:+d}) → 사이클완성→{nv}', 0.80
    nv = 1 - runs[-1][0]
    return nv, f'계단식[{s}] 런={lens}(Δ{step:+d}) → 다음런={nv}×{next_len}', 0.82

def check_history_match(seq, full_history):
    """현재 seq tail을 전체 과거 히스토리에서 검색해 다음 값 예측
    - exact match: 히스토리에서 seq와 동일한 구간 찾기 → 그 다음 값
    - complement match: seq의 비트반전을 검색 → 예측값도 반전
    반환: (예측값 or None, 설명 or None, 점수)
    """
    clean_h = [x for x in full_history if x in (0, 1)]
    n = len(seq)
    if len(clean_h) <= n or n < 3:
        return None, None, 0.0

    s = ''.join(str(x) for x in seq)

    # Exact match
    matches = []
    for i in range(len(clean_h) - n):
        if clean_h[i:i+n] == list(seq):
            matches.append(clean_h[i+n])

    label = '히스토리조회'
    complement = False

    if not matches:
        comp = [1 - x for x in seq]
        for i in range(len(clean_h) - n):
            if clean_h[i:i+n] == comp:
                matches.append(1 - clean_h[i+n])
        if matches:
            complement = True
            label = '보수조회'

    if not matches:
        return None, None, 0.0

    ones = sum(matches)
    zeros = len(matches) - ones
    nv = 1 if ones > zeros else 0
    vote_ratio = max(ones, zeros) / len(matches)
    comp_tag = '(보수)' if complement else ''
    desc = f'{label}{comp_tag}[{s}] {len(matches)}회매칭→{nv}({vote_ratio:.0%})'
    score = 0.68 + vote_ratio * 0.16  # 0.68~0.84
    return nv, desc, score

def check_meta_alternating(seq, full_history=None):
    """계단식↔짝맞춤 교대 메타패턴 감지

    현재 seq를 S(계단식)/P(짝맞춤) 구간으로 분할:
      3분할: S→P→S 또는 P→S→P → 중간 타입이 다음에도 반복 (score 0.85)
      2분할: S→P 또는 P→S → 처음 타입이 다음에 재등장 (score 0.80)
    마지막 구간의 반대 타입 예측 로직을 seq에 적용해 다음 값 반환
    """
    n = len(seq)
    if n < 8:
        return None, None, 0.0

    def _classify(b):
        if len(b) < 4:
            return None, 0.0
        _, _, s_sc = check_staircase_pattern(b)
        if s_sc >= 0.78:
            return 'S', s_sc
        _, _, rm_sc = check_run_mirror_pattern(b)
        if rm_sc >= 0.78:
            return 'P', rm_sc
        rl = [r[1] for r in find_runs(b)]
        if len(rl) >= 3 and rl == rl[::-1]:
            return 'P', 0.75
        return None, 0.0

    clean_h = [x for x in (full_history or []) if x in (0, 1)]

    # ── 3분할: S→P→S 또는 P→S→P ──────────────────────────────
    found3 = None
    for i in range(4, n - 8):
        t1, sc1 = _classify(seq[:i])
        if t1 is None:
            continue
        for j in range(i + 4, n - 4):
            t2, sc2 = _classify(seq[i:j])
            t3, sc3 = _classify(seq[j:])
            if t2 and t3 and t1 != t2 and t2 != t3 and t1 == t3:
                # (chain, next_t, avg_sc, split_j)
                found3 = ([t1, t2, t3], t2, (sc1 + sc2 + sc3) / 3, j)
                break
        if found3:
            break

    if found3:
        chain, next_t, avg_sc, split_j = found3
        last_seg = list(seq[split_j:])
        last_t   = chain[-1]   # 마지막 구간 타입
        base     = min(0.85, avg_sc + 0.03)
    else:
        # ── 2분할: S→P 또는 P→S ───────────────────────────────
        found2 = None
        for i in range(4, n - 4):
            t1, sc1 = _classify(seq[:i])
            t2, sc2 = _classify(seq[i:])
            if t1 and t2 and t1 != t2:
                found2 = ([t1, t2], t1, (sc1 + sc2) / 2, i)
                break
        if not found2:
            return None, None, 0.0
        chain, next_t, avg_sc, split_i = found2
        last_seg = list(seq[split_i:])
        last_t   = chain[-1]
        base     = min(0.80, avg_sc + 0.02)

    chain_str = '→'.join(chain) + f'→[{next_t}]'

    # 마지막 구간의 타입 예측 로직을 last_seg에 적용
    if last_t == 'S':
        nv, d, sc = check_staircase_pattern(last_seg)
    else:  # P
        nv, d, sc = check_run_mirror_pattern(last_seg)
        if nv is None and clean_h:
            nv, d, sc = check_history_match(last_seg, clean_h)

    if nv is None:
        return None, None, 0.0
    return nv, f'교대메타[{chain_str}] {d}', base

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

def analyze_pattern(seq, full_history=None):
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

    run_mir_val, run_mir_desc, run_mir_score = check_run_mirror_pattern(seq)
    if run_mir_val is not None:
        candidates.append({'type':'런분할',
                           'desc': run_mir_desc,
                           'rec':  run_mir_val,
                           'score': run_mir_score})

    stair_val, stair_desc, stair_score = check_staircase_pattern(seq)
    if stair_val is not None:
        candidates.append({'type':'계단식',
                           'desc': stair_desc,
                           'rec':  stair_val,
                           'score': stair_score})

    if full_history is not None:
        # 다양한 tail 길이로 히스토리 조회 (최소 4, 최대 현재 seq 길이)
        best_hm = (None, None, 0.0)
        for tail_len in range(min(n, 12), 3, -1):
            tail_seq = seq[-tail_len:]
            hm_val, hm_desc, hm_score = check_history_match(tail_seq, full_history)
            if hm_val is not None and hm_score > best_hm[2]:
                best_hm = (hm_val, hm_desc, hm_score)
                break  # 가장 긴 tail에서 매칭된 것 우선
        if best_hm[0] is not None:
            candidates.append({'type':'짝맞춤',
                               'desc': best_hm[1],
                               'rec':  best_hm[0],
                               'score': best_hm[2]})

        # 교대 메타패턴 (계단식↔짝맞춤 교대)
        meta_val, meta_desc, meta_score = check_meta_alternating(seq, full_history)
        if meta_val is not None:
            candidates.append({'type':'교대메타',
                               'desc': meta_desc,
                               'rec':  meta_val,
                               'score': meta_score})

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
from datetime import datetime as _dt, timedelta as _td

def normalize_date(raw):
    """'Today, 25 Apr' / 'Yesterday, 24 Apr' / '21 Apr 2026' → 'YYYY-MM-DD'"""
    s = str(raw).strip()
    today = _dt.today()
    if s.startswith('Today'):
        return today.strftime('%Y-%m-%d')
    if s.startswith('Yesterday'):
        return (today - _td(days=1)).strftime('%Y-%m-%d')
    # 'DD Mon YYYY' 또는 'DD Mon YYYY - ...' 형태
    date_part = s.split(' - ')[0].strip()
    for fmt in ('%d %b %Y', '%d %B %Y'):
        try:
            return _dt.strptime(date_part, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s  # 변환 불가 시 원본 반환

print('데이터 로드 중...')
df = pd.read_csv(CSV_PATH)
df['date'] = df['date'].apply(normalize_date)
df['direction'] = df['consensus'].map({'home': 1, 'away': 0})
date_map = {d: i for i, d in enumerate(sorted(df['date'].unique()))}
df['date_order'] = df['date'].map(date_map)
df = df.sort_values(['date_order', 'slot', 'bookmaker']).reset_index(drop=True)

# ── 경기 단위 집계 (북메이커 전체 기준) ─────────────────────
meta = df.drop_duplicates('match_id')[
    ['match_id', 'date', 'date_order', 'slot',
     'home', 'away', 'winner', 'winner_is_home']
].set_index('match_id')

bm_agg = df.groupby('match_id').agg(
    bm_count      = ('bookmaker',   'count'),
    home_pct      = ('consensus',   lambda x: (x == 'home').mean()),   # 홈 지지 북메이커 비율
    avg_home_odds = ('home_close',  'mean'),
    avg_away_odds = ('away_close',  'mean'),
    std_home_odds = ('home_close',  'std'),
    std_away_odds = ('away_close',  'std'),
)

game_df = meta.join(bm_agg).reset_index().sort_values('date_order').reset_index(drop=True)

# 다수결 컨센서스 (50% 초과면 home)
game_df['consensus']     = game_df['home_pct'].apply(lambda p: 'home' if p > 0.5 else 'away')
# 컨센서스 강도: 0.5~1.0 → 얼마나 강한 쏠림인지
game_df['consensus_str'] = (game_df['home_pct'] - 0.5).abs() * 2   # 0=중립, 1=만장일치
# 컨센서스가 이긴 경우
game_df['consensus_win'] = (
    ((game_df['consensus'] == 'home') &  game_df['winner_is_home']) |
    ((game_df['consensus'] == 'away') & ~game_df['winner_is_home'])
).astype(int)

# ── Postp(연기) 경기를 game_df에 병합 ───────────────────────
# kbo_games.csv의 과거 날짜 중 winner=null, slot 있는 행 → Postp로 처리
if os.path.exists(GAMES_PATH):
    _gdf = pd.read_csv(GAMES_PATH)
    _today = datetime.today().strftime('%Y-%m-%d')
    _existing_slots = set(zip(game_df['date'], game_df['slot'].apply(lambda x: str(float(x)))))
    _postp = _gdf[
        _gdf['winner'].isna() &
        (_gdf['date'] < _today) &
        _gdf['slot'].notna()
    ].copy()
    _postp_rows = []
    for _, r in _postp.iterrows():
        key = (r['date'], str(float(r['slot'])))
        if key not in _existing_slots:
            _postp_rows.append({
                'match_id':      f'postp_{r["date"]}_s{int(r["slot"])}',
                'date':          r['date'],
                'date_order':    date_map.get(r['date'], -1),
                'slot':          float(r['slot']),
                'home':          r['home'],
                'away':          r['away'],
                'winner':        'Postp',
                'winner_is_home': float('nan'),
                'bm_count':      0,
                'home_pct':      float('nan'),
                'avg_home_odds': float('nan'),
                'avg_away_odds': float('nan'),
                'std_home_odds': float('nan'),
                'std_away_odds': float('nan'),
                'consensus':     'Postp',
                'consensus_str': float('nan'),
                'consensus_win': float('nan'),
            })
    if _postp_rows:
        _pdf = pd.DataFrame(_postp_rows)
        game_df = pd.concat([game_df, _pdf], ignore_index=True)\
                    .sort_values('date_order').reset_index(drop=True)
        print(f'Postp 경기 {len(_postp_rows)}개 병합')

print(f'데이터 로드: {len(df)}행 | {len(date_map)}일치 | {len(game_df)}경기')


# ── 팀 기반 시퀀스 함수 ───────────────────────────────────
def get_team_triple_seq(team, before_date_order, window=WINDOW):
    """팀 최근 경기 4개 시퀀스 반환:
    - direction    : 북메이커 다수결로 팀이 정배(1) or 역배(0)
    - bm_agreement : 북메이커 의견 일치(1=강한 쏠림≥70%) or 분산(0=분열<70%)
    - fav_win      : 정배팀 승(1) or 역배팀 승(0)
    - team_win     : 해당 팀 승(1) or 패(0)
    """
    mask = (
        ((game_df['home'] == team) | (game_df['away'] == team)) &
        (game_df['date_order'] < before_date_order) &
        (game_df['winner'] != 'Postp')   # Postp 경기는 팀 시퀀스에서 제외
    )
    recent = game_df[mask].sort_values('date_order').tail(window)
    direction_seq, agree_seq, fav_win_seq, team_win_seq = [], [], [], []
    for _, r in recent.iterrows():
        is_fav = (
            (r['consensus'] == 'home' and r['home'] == team) or
            (r['consensus'] == 'away' and r['away'] == team)
        )
        direction_seq.append(1 if is_fav else 0)
        # 강한 쏠림: 북메이커 70% 이상 동일 방향이면 1 (consensus_str >= 0.4)
        cstr = r.get('consensus_str', 0)
        agree_seq.append(1 if (cstr and not pd.isna(cstr) and cstr >= 0.4) else 0)
        cw = r['consensus_win']
        fav_win_seq.append(int(cw) if not pd.isna(cw) else 0)
        team_win_seq.append(1 if r['winner'] == team else 0)
    return direction_seq, agree_seq, fav_win_seq, team_win_seq

def get_slot_fav_win_seq(slot, before_date_order, window=WINDOW):
    """해당 슬롯(N번째 경기)의 날짜별 정배승(1)/역배승(0) 시퀀스
    Ex) 2번째 경기: 20일→1, 21일→0, 22일→1, 23일→1, 24일→1 → 오늘 예측
    """
    mask = (
        (game_df['slot'] == slot) &
        (game_df['date_order'] < before_date_order) &
        (game_df['winner'] != 'Postp')   # Postp 경기는 정배/역배 시퀀스에서 제외
    )
    recent = game_df[mask].sort_values('date_order').tail(window)
    return recent['consensus_win'].tolist(), recent['date'].tolist()

def get_team_win_seq(team, before_date_order, window=WINDOW):
    _, _, _, team_win = get_team_triple_seq(team, before_date_order, window)
    return team_win

def get_team_fav_seq(team, before_date_order, window=WINDOW):
    direction, _, _, _ = get_team_triple_seq(team, before_date_order, window)
    return direction

def make_feat_team(home, away, before_date_order):
    """홈팀 + 원정팀 시퀀스 피처 벡터 (6 × WINDOW)"""
    def pad(seq):
        return [-1] * (WINDOW - len(seq)) + seq

    h_dir, h_agr, h_fav, hw = get_team_triple_seq(home, before_date_order)
    a_dir, a_agr, a_fav, aw = get_team_triple_seq(away, before_date_order)
    return pad(hw) + pad(aw) + pad(h_dir) + pad(a_dir) + pad(h_agr) + pad(a_agr)

def seq_str(seq):
    return ''.join(str(x) for x in seq) if seq else '-'

def pat_rec(seq, full_history=None):
    """시퀀스 패턴 분석 → (추천값 or None, 설명문자열)"""
    if len(seq) < 3:
        return None, '데이터 부족'
    pa = analyze_pattern(seq, full_history=full_history)
    rec = pa['rec'] if not pa.get('pass') else None
    return rec, pa['desc']

def get_bm_odds_seqs(team, before_date_order, window=WINDOW):
    """북메이커별 해당 팀 배당 변동 방향 시퀀스 반환
    - 경기마다 배당이 이전 경기 대비 내렸으면 1(유리해짐), 올랐으면 0(불리해짐)
    - 첫 경기는 기준점이므로 방향값 없음 → window+1 경기 수집 후 diff
    반환: {bookmaker: {dates, odds, seq, current_odds}}
    """
    mask = (
        ((game_df['home'] == team) | (game_df['away'] == team)) &
        (game_df['date_order'] < before_date_order)
    )
    # window+1 경기 수집 (첫 경기는 기준점용)
    recent_games = game_df[mask].sort_values('date_order').tail(window + 1)
    if len(recent_games) < 2:
        return {}

    match_ids = recent_games['match_id'].tolist()
    dates_map = recent_games.set_index('match_id')['date'].to_dict()

    bm_data = df[df['match_id'].isin(match_ids)][
        ['match_id', 'bookmaker', 'home', 'away', 'home_close', 'away_close']
    ].copy()

    # 북메이커별로 경기순 배당값 수집
    raw = {}  # {bm: [(mid, date, team_odds), ...]}
    mid_order = {mid: i for i, mid in enumerate(match_ids)}
    for _, r in bm_data.iterrows():
        bm  = r['bookmaker']
        mid = r['match_id']
        team_odds = r['home_close'] if r['home'] == team else r['away_close']
        opp_odds  = r['away_close'] if r['home'] == team else r['home_close']
        if bm not in raw:
            raw[bm] = []
        raw[bm].append({
            'mid': mid, 'date': dates_map.get(mid, ''),
            'team_odds': round(float(team_odds), 2),
            'opp_odds':  round(float(opp_odds),  2),
            'order': mid_order.get(mid, 99),
        })

    result = {}
    for bm, entries in raw.items():
        entries.sort(key=lambda x: x['order'])
        if len(entries) < 2:
            continue
        odds_list = [e['team_odds'] for e in entries]
        date_list = [e['date']      for e in entries]
        opp_list  = [e['opp_odds']  for e in entries]
        # 방향 시퀀스: 1=내림(유리), 0=오름(불리), -1=동일(제외)
        seq = []
        for i in range(1, len(odds_list)):
            if odds_list[i] < odds_list[i-1]:
                seq.append(1)   # 배당 하락 = 해당 팀 더 유리
            elif odds_list[i] > odds_list[i-1]:
                seq.append(0)   # 배당 상승 = 해당 팀 불리
            # 동일이면 추가 안 함 (변동 없음)
        result[bm] = {
            'seq':          seq,
            'odds':         odds_list[1:],   # 방향 대응 배당값 (기준점 제외)
            'odds_full':    odds_list,        # 전체 (기준 포함)
            'dates':        date_list[1:],
            'current_odds': odds_list[-1],
            'opp_odds':     opp_list[-1],
        }
    return result

def get_slot_bm_odds_seqs(slot, before_date_order, seq_len=BM_SEQ_LEN):
    """슬롯(N번째 경기) 기준 날짜별 북메이커 배당 변동 시퀀스

    신호 추출 (북메이커별):
      winner_change = home_close-home_open  if 홈승 else away_close-away_open
      loser_change  = 반대편
      · winner_change > loser_change → 1
      · winner_change < loser_change → 0
      · 그 외(동일값 / open없음 / 둘다변동없음 / 북메이커누락) → N

    N 조건:
      1. open 데이터 없음 (해당 경기에 open 미수집)
      2. 홈/원정 둘 다 open==close (양쪽 모두 변동 없음)
      3. winner_change == loser_change (변동 동일)
      4. 해당 경기에 북메이커 데이터 자체 없음
    """
    mask = (game_df['slot'] == slot) & (game_df['date_order'] < before_date_order)
    all_games = game_df[mask].sort_values('date_order')
    if len(all_games) < 1:
        return {}

    match_ids       = all_games['match_id'].tolist()
    dates_map       = all_games.set_index('match_id')['date'].to_dict()
    winner_home_map = all_games.set_index('match_id')['winner_is_home'].to_dict()

    bm_data = df[df['match_id'].isin(match_ids)][
        ['match_id', 'bookmaker',
         'home_open', 'home_close',
         'away_open', 'away_close']
    ].copy()

    # 북메이커별 경기 데이터 인덱싱
    bm_mid_map = {}
    for _, r in bm_data.iterrows():
        bm  = r['bookmaker']
        mid = r['match_id']
        if bm not in bm_mid_map:
            bm_mid_map[bm] = {}
        bm_mid_map[bm][mid] = {
            'h_open':  None if pd.isna(r['home_open'])  else float(r['home_open']),
            'h_close': None if pd.isna(r['home_close']) else float(r['home_close']),
            'a_open':  None if pd.isna(r['away_open'])  else float(r['away_open']),
            'a_close': None if pd.isna(r['away_close']) else float(r['away_close']),
        }

    # Postp 경기 match_id 집합
    postp_mids = set(all_games[all_games['winner'] == 'Postp']['match_id'].tolist())

    result = {}
    for bm, mid_data in bm_mid_map.items():
        all_seq      = []
        all_date_seq = []

        for mid in match_ids:
            date = dates_map.get(mid, '')
            wih  = winner_home_map.get(mid)
            sig  = 'N'

            if mid not in mid_data:
                # Postp 경기: 북메이커 데이터 없고 연기된 게임
                if mid in postp_mids:
                    all_seq.append('P')
                else:
                    all_seq.append('N')
                all_date_seq.append(date)
                continue

            e = mid_data[mid]
            h_open, h_close = e['h_open'], e['h_close']
            a_open, a_close = e['a_open'], e['a_close']

            w_is_home = (wih is True or wih == 1)

            # open 없으면 N
            h_chg = round(h_close - h_open, 4) if (h_open is not None and h_close is not None) else None
            a_chg = round(a_close - a_open, 4) if (a_open is not None and a_close is not None) else None

            if h_chg is None or a_chg is None:
                all_seq.append('N')
                all_date_seq.append(date)
                continue

            w_chg = h_chg if w_is_home else a_chg
            l_chg = a_chg if w_is_home else h_chg

            if   w_chg > l_chg: sig = 1
            elif w_chg < l_chg: sig = 0

            all_seq.append(sig)
            all_date_seq.append(date)

        if not any(x != 'N' for x in all_seq):
            continue

        seq      = all_seq[-seq_len:]
        date_seq = all_date_seq[-seq_len:]
        current  = next(
            (mid_data[mid]['h_close'] for mid in reversed(match_ids)
             if mid in mid_data and mid_data[mid]['h_close'] is not None),
            None
        )

        result[bm] = {
            'seq':          seq,
            'full_seq':     all_seq,   # 히스토리 조회용 전체 시퀀스
            'dates':        date_seq,
            'current_odds': current,
        }
    return result

def analyze_slot_bm_seqs(slot, before_date_order):
    """슬롯 기준 북메이커별 배당 변동 패턴 분석"""
    bm_seqs = get_slot_bm_odds_seqs(slot, before_date_order)
    results = []
    for bm, data in sorted(bm_seqs.items()):
        seq       = data['seq']
        full_seq  = data.get('full_seq', [])
        seq_clean = [x for x in seq      if x not in ('N', 'P')]
        full_clean = [x for x in full_seq if x in (0, 1)]
        rec, desc = pat_rec(seq_clean, full_history=full_clean if len(full_clean) > len(seq_clean) else None)
        results.append({
            'bm':           bm,
            'seq':          seq,
            'rec':          rec,
            'desc':         desc,
            'dates':        data['dates'],
            'current_odds': data['current_odds'],
        })
    return results

def analyze_bm_seqs(team, before_date_order, window=WINDOW):
    """북메이커별 배당 변동 패턴 분석
    반환: list of {bm, seq, rec, desc, odds_full, current_odds, opp_odds}
    """
    bm_seqs = get_bm_odds_seqs(team, before_date_order, window)
    results = []
    for bm, data in sorted(bm_seqs.items()):
        seq  = data['seq']
        rec, desc = pat_rec(seq)
        results.append({
            'bm':          bm,
            'seq':         seq,
            'rec':         rec,
            'desc':        desc,
            'odds_full':   data['odds_full'],
            'odds':        data['odds'],
            'dates':       data['dates'],
            'current_odds': data['current_odds'],
            'opp_odds':    data['opp_odds'],
        })
    return results


# ── ML 모델 학습 ──────────────────────────────────────────
print('ML 모델 학습 중...')
X_list, y_list = [], []
for _, g in game_df.sort_values('date_order').iterrows():
    if g.get('winner') == 'Postp' or pd.isna(g['winner_is_home']):
        continue  # Postp 또는 결과 없는 경기 스킵
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

    # 오늘~7일 내 결과 없는 경기일 탐색 (winner가 없는 = 예정/미완료 경기)
    for delta in range(0, 8):
        target = (latest_dt + timedelta(days=delta)).strftime('%Y-%m-%d')
        day_games = gdf[(gdf['date'] == target) & (gdf['winner'].isna())]
        if len(day_games) > 0:
            return day_games.to_dict('records'), target

    return [], None

if globals().get('_BACKTEST_ONLY', False):
    raise SystemExit(0)  # backtest 모드: 함수/모델 로드만 하고 종료

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

    # 팀별 4개 시퀀스 수집
    h_dir, h_agr, h_fav_win, h_team_win = get_team_triple_seq(home, max_date_order)
    a_dir, a_agr, a_fav_win, a_team_win = get_team_triple_seq(away, max_date_order)

    # 슬롯별 정배승/역배승 시퀀스 (N번째 경기 날짜별 추이)
    slot_fav_seq, slot_fav_dates = get_slot_fav_win_seq(slot, max_date_order)

    # 패턴 분석 (각 팀 × 4 시퀀스)
    h_dir_rec,  h_dir_desc  = pat_rec(h_dir)
    h_agr_rec,  h_agr_desc  = pat_rec(h_agr)
    h_faw_rec,  h_faw_desc  = pat_rec(h_fav_win)
    h_win_rec,  h_win_desc  = pat_rec(h_team_win)

    slot_fav_rec, slot_fav_desc = pat_rec(slot_fav_seq)

    a_dir_rec,  a_dir_desc  = pat_rec(a_dir)
    a_agr_rec,  a_agr_desc  = pat_rec(a_agr)
    a_faw_rec,  a_faw_desc  = pat_rec(a_fav_win)
    a_win_rec,  a_win_desc  = pat_rec(a_team_win)

    # 현재 경기 북메이커 통계 (game_df의 가장 최신 행 재사용)
    def bm_summary(team, is_home):
        last = game_df[
            ((game_df['home'] == team) | (game_df['away'] == team))
        ].sort_values('date_order').tail(1)
        if len(last) == 0:
            return ''
        r = last.iloc[0]
        pct = r['home_pct'] if is_home else 1 - r['home_pct']
        n   = int(r['bm_count'])
        favoring = round(pct * n)
        return f'최근경기 {favoring}/{n}북메이커({pct:.0%}) 지지'

    def fmt_rec(rec):
        if rec is None: return ' ?'
        return f' {rec}'

    print(f'\n{"="*68}')
    print(f'  {home}  vs  {away}')
    print(f'{"="*68}')
    print(f'  {"항목":<18} {"홈팀 "+home[:14]+" 시퀀스":^24}  {"원정팀 "+away[:12]+" 시퀀스":^24}')
    print(f'  {"-"*66}')

    # 1) 정배여부 (북메이커 다수결: 해당팀 정배=1, 역배=0)
    h_d = seq_str(h_dir); a_d = seq_str(a_dir)
    print(f'  {"정배여부(다수결)":<18} [{h_d}]→{fmt_rec(h_dir_rec):<3}  [{a_d}]→{fmt_rec(a_dir_rec)}')
    print(f'  {"":18} {bm_summary(home, True)}')
    print(f'  {"":18} {bm_summary(away, False)}')

    # 2) 북메이커 일치도 (1=강한쏠림≥70%, 0=분열<70%)
    h_ag = seq_str(h_agr); a_ag = seq_str(a_agr)
    print(f'  {"북메이커 일치도":<18} [{h_ag}]→{fmt_rec(h_agr_rec):<3}  [{a_ag}]→{fmt_rec(a_agr_rec)}')
    print(f'  {"":18} (1=70%↑ 쏠림, 0=의견분열)')

    # 3) 슬롯별 정배승(1)/역배승(0) — 날짜별 N번째 경기 기준 통합
    sf = seq_str(slot_fav_seq)
    date_labels = ' '.join(d.replace('Yesterday, ','').replace('Today','오늘')[-5:] for d in slot_fav_dates[-len(slot_fav_seq):])
    print(f'  {"정배승/역배승":<18} [{sf}]→{fmt_rec(slot_fav_rec):<3}  (슬롯{slot} 날짜별: {date_labels})')
    print(f'  {"":18} {slot_fav_desc}')

    # 4) 팀 승(1) / 패(0)
    h_tw = seq_str(h_team_win); a_tw = seq_str(a_team_win)
    print(f'  {"팀 승패":<18} [{h_tw}]→{fmt_rec(h_win_rec):<3}  [{a_tw}]→{fmt_rec(a_win_rec)}')
    print(f'  {"":18} {h_win_desc}')
    print(f'  {"":18} {a_win_desc}')

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

    # ── 슬롯 기준 북메이커 배당변동 (날짜별 N번째 경기) ────────────
    print(f'\n  ▶ [슬롯{slot}] 날짜별 북메이커 배당변동 (1=배당+오름, 0=배당-내림)')
    print(f'  {"북메이커":<16} {"시퀀스":<{BM_SEQ_LEN+2}} {"예측":^5} {"날짜흐름"}')
    print(f'  {"-"*70}')
    slot_bm_analyses = analyze_slot_bm_seqs(slot, max_date_order)
    slot_bm_results = {}
    for entry in slot_bm_analyses:
        s   = seq_str(entry['seq'])
        rec = entry['rec']
        rec_sym = f'→{rec}' if rec is not None else '→?'
        dates_short = [d[-5:] if len(d) >= 5 else d for d in entry['dates']]
        date_flow = ' '.join(dates_short)
        print(f'  {entry["bm"]:<16} [{s}]{rec_sym:<4} {date_flow}')
        slot_bm_results[entry['bm']] = {
            'seq': s, 'rec': rec, 'desc': entry['desc'],
            'current_odds': entry.get('current_odds'),
        }
    # 슬롯 북메이커 집계
    s_recs = [e['rec'] for e in slot_bm_analyses if e['rec'] is not None]
    if s_recs:
        sv1 = sum(s_recs); sv0 = len(s_recs) - sv1
        print(f'\n  → 슬롯{slot} 집계: 배당↑(1) {sv1}개 / 배당↓(0) {sv0}개 (총 {len(s_recs)}개)')

    predictions[f'slot_{slot}'] = {
        'slot':            slot,
        'home':            home,
        'away':            away,
        'pred_date':       pred_date,
        # 홈팀 4 시퀀스
        'home_direction':  seq_str(h_dir),
        'home_bm_agree':   seq_str(h_agr),
        'home_fav_win':    seq_str(h_fav_win),
        'home_team_win':   seq_str(h_team_win),
        'home_dir_rec':    h_dir_rec,
        'home_agr_rec':    h_agr_rec,
        'home_fav_rec':    h_faw_rec,
        'home_win_rec':    h_win_rec,
        # 원정팀 4 시퀀스
        'away_direction':  seq_str(a_dir),
        'away_bm_agree':   seq_str(a_agr),
        'away_fav_win':    seq_str(a_fav_win),
        'away_team_win':   seq_str(a_team_win),
        'away_dir_rec':    a_dir_rec,
        'away_agr_rec':    a_agr_rec,
        'away_fav_rec':    a_faw_rec,
        'away_win_rec':    a_win_rec,
        'slot_fav_win':    seq_str(slot_fav_seq),
        'slot_fav_rec':    slot_fav_rec,
        'slot_bm':         slot_bm_results,
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
