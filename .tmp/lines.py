import io, re
p = '/tmp/ds_out/final.txt'
lines = io.open(p, encoding='utf-8', errors='replace').read().split('\n')
print('total lines(excl trailing):', len([l for l in lines if l.strip()]) if False else len(lines) - (1 if lines and lines[-1] == '' else 0))
n_idx = sum(1 for l in lines if l.startswith('Index'))
n_num = sum(1 for l in lines if re.match(r'^\s*-?\d+\s', l))
n_blank = sum(1 for l in lines if not l.strip())
print('Index headers:', n_idx, '| numeric-leading rows:', n_num, '| blank:', n_blank)
print('--- first 12 lines ---')
for l in lines[:12]:
    print(repr(l[:100]))
