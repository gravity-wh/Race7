# -*- coding: utf-8 -*-
import io, os, hashlib, re, sys

home = os.path.expanduser('~')
text = io.open(os.path.join(home, 'PublicCase/HANDOFF.md'), encoding='utf-8').read()
recorded = set(re.findall(r'\b[0-9a-f]{32}\b', text))

root = sys.argv[1]
files = []
for dp, dns, fns in os.walk(root):
    for fn in fns:
        fp = os.path.join(dp, fn)
        if os.path.islink(fp):
            continue
        files.append(fp)
files.sort()
print('files:', len(files))

recs = []
for fp in files:
    h = hashlib.sha256()
    with open(fp, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    rel = os.path.relpath(fp, root)
    recs.append((rel, h.hexdigest()))

def md5(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()

combos = {}
for prefix in ('', './'):
    for fmt in ('%s  %s', '%s %s', '%s%s', '%s\t%s'):
        combos['%s|%r' % (prefix or '.', fmt)] = md5(''.join(fmt % (h, prefix + p) for p, h in recs))
        combos['%s|pfirst|%r' % (prefix or '.', fmt)] = md5(''.join(fmt % (prefix + p, h) for p, h in recs))
combos['sha_only'] = md5(''.join(h for p, h in recs))
combos['path_only'] = md5(''.join(p for p, h in recs))
combos['sha_only_nl'] = md5('\n'.join(h for p, h in recs))
combos['p_h_nl'] = md5('\n'.join('%s  %s' % (p, h) for p, h in recs))
combos['h_p_nl'] = md5('\n'.join('%s  %s' % (h, p) for p, h in recs))

hits = 0
for k, v in combos.items():
    if v in recorded:
        print('MATCH', k, v); hits += 1
print('hits:', hits)
print('sample:', list(combos.items())[:3])
