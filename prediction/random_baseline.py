"""P2: 무작위 0/1 시퀀스에서 각 패턴의 발화율 측정.
패턴이 무작위 시퀀스에서도 자주 발화하면 base_w를 깎아야 함.
"""
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os, random, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 패턴 함수 import (수동, 부작용 회피)
import importlib.util
spec = importlib.util.spec_from_file_location('kp', 'kbo_predict.py')
# kbo_predict.py를 직접 import하면 데이터 로딩이 트리거되므로
# 패턴 함수들만 수동으로 추출
import importlib.machinery
loader = importlib.machinery.SourceFileLoader('kp_funcs', 'kbo_predict.py')
# 무거운 import 회피 위해 ast로 함수만 추출
import ast, types
with open('kbo_predict.py', encoding='utf-8') as f:
    src = f.read()
tree = ast.parse(src)
pattern_funcs_src = []
target_names = [
    'find_runs', 'check_mirror', 'check_repeat_block', 'check_palindrome',
    'check_alternating', 'check_block_split', 'check_tail_split_mirror',
    'check_palindrome_build', 'check_alternating_pairs', 'check_tail_cyclic',
    'check_fold_palindrome_tail', 'check_double_fold', 'check_fold_mirror',
    'check_inner_palindrome', 'check_run_shape', 'check_run_mirror_pattern',
    'check_staircase_pattern', 'check_run_length_balancer',
    'check_rolling_momentum'
]
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in target_names:
        pattern_funcs_src.append(ast.get_source_segment(src, node))

# 동적 실행
mod_ns = {}
exec('\n\n'.join(pattern_funcs_src), mod_ns)

N_TRIALS = 10000
SEQ_LEN = 17
random.seed(42)

# 무작위 시퀀스 풀
seqs = [[random.randint(0,1) for _ in range(SEQ_LEN)] for _ in range(N_TRIALS)]

results = {}

def fires_simple(name, fn):
    """단순 bool 반환 패턴"""
    fires = 0
    for s in seqs:
        try:
            r = fn(s)
            if r: fires += 1
        except Exception:
            pass
    return fires / N_TRIALS

def fires_struct(name, fn, accept_none=True):
    """튜플/객체 반환 패턴 — 첫 요소가 None이 아니면 발화"""
    fires = 0
    for s in seqs:
        try:
            r = fn(s)
            if r is None: continue
            if isinstance(r, tuple) and len(r) >= 1 and r[0] is not None:
                fires += 1
            elif not isinstance(r, tuple) and r is not None:
                # check_palindrome 등 단순 True/False
                if r: fires += 1
        except Exception:
            pass
    return fires / N_TRIALS

# 패턴별 측정
tests = [
    ('전체연속',   lambda s: len(set(s))==1),
    ('교차',       mod_ns['check_alternating']),
    ('반복블록',   mod_ns['check_repeat_block']),
    ('블록분할',   mod_ns['check_block_split']),
    ('꼬리분할미러', mod_ns['check_tail_split_mirror']),
    ('팰린드롬확장', mod_ns['check_palindrome_build']),
    ('교차쌍',     mod_ns['check_alternating_pairs']),
    ('꼬리주기',   mod_ns['check_tail_cyclic']),
    ('접기팰꼬리', mod_ns['check_fold_palindrome_tail']),
    ('Fold Mirror',mod_ns['check_fold_mirror']),
    ('런분할미러', mod_ns['check_run_mirror_pattern']),
    ('런밸런서',   mod_ns['check_run_length_balancer']),
    ('롤링모멘텀', mod_ns['check_rolling_momentum']),
]

print(f'무작위 시퀀스 {N_TRIALS}개 (길이 {SEQ_LEN}) 각 패턴 발화율 측정')
print('-' * 70)
print(f'{"패턴":<16} {"발화율":>10} {"발화율(%)":>10}  {"권장 base_w 보정":<20}')
print('-' * 70)

for name, fn in tests:
    if name == '전체연속':
        rate = fires_simple(name, fn)
    elif name in ('반복블록', '블록분할'):
        # 튜플 또는 None 반환
        fires = 0
        for s in seqs:
            try:
                r = fn(s)
                if r is not None: fires += 1
            except: pass
        rate = fires / N_TRIALS
    elif name == 'Fold Mirror':
        # 리스트 반환
        fires = 0
        for s in seqs:
            try:
                r = fn(s)
                if r and len(r) > 0: fires += 1
            except: pass
        rate = fires / N_TRIALS
    else:
        rate = fires_struct(name, fn)
    results[name] = rate
    # 권장: 발화율 > 20%이면 (1 - rate) 배율 적용
    if rate > 0.20:
        suggestion = f'×{1-rate:.2f} (현저)'
    elif rate > 0.10:
        suggestion = f'×{1-rate*0.7:.2f} (경도)'
    else:
        suggestion = '유지'
    print(f'{name:<16} {rate:>10.4f} {rate*100:>9.2f}%  {suggestion:<20}')

# JSON 저장
with open('pattern_random_rate.json', 'w', encoding='utf-8') as f:
    json.dump({'n_trials': N_TRIALS, 'seq_len': SEQ_LEN, 'rates': results}, f, ensure_ascii=False, indent=2)
print(f'\n저장: pattern_random_rate.json')
