# -*- coding: utf-8 -*-
import io, os, hashlib, re, itertools, glob

home = os.path.expanduser('~')
text = io.open(os.path.join(home, 'PublicCase/HANDOFF.md'), encoding='utf-8').read()
recorded = set(re.findall(r'\b[0-9a-f]{32}\b', text))
print('recorded fingerprints:', len(recorded))

def cands(manpath):
    lines = [l.rstrip('\n') for l in io.open(manpath, encoding='utf-8') if l.strip() and not l.startswith('#')]
    pairs = []
    for l in lines:
        h, _, p = l.partition('  ')
        pairs.append((p, h))
    out = {}
    def md5(s):
        return hashlib.md5(s.encode('utf-8')).hexdigest()
    raw = [l for l in io.open(manpath, encoding='utf-8').read().split('\n') if l.strip() and not l.startswith('#')]
    out['raw_join'] = md5('\n'.join(raw))
    out['raw_join_nl'] = md5('\n'.join(raw) + '\n')
    sp = sorted(pairs)
    out['sorted_h2p'] = md5('\n'.join('%s  %s' % (h, p) for p, h in sp))
    out['sorted_h2p_nl'] = md5('\n'.join('%s  %s' % (h, p) for p, h in sp) + '\n')
    out['sorted_php'] = md5(''.join('%s%s' % (p, h) for p, h in sp))
    out['sorted_hp'] = md5(''.join('%s%s' % (h, p) for p, h in sp))
    out['paths'] = md5(''.join(p for p, h in sorted(pairs)))
    out['sha_join'] = md5(''.join(h for p, h in sorted(pairs)))
    return out

for m in glob.glob(os.path.join(home, '*presubmission_eda260769/MANIFEST.txt')) + \
         glob.glob(os.path.join(home, '*/*/presubmission_eda260769/MANIFEST.txt')):
    c = cands(m)
    hit = {k: v for k, v in c.items() if v in recorded}
    print('\n==', m, 'entries:', sum(1 for _ in io.open(m, encoding='utf-8')))
    for k, v in c.items():
        print('  %-14s %s %s' % (k, v, '<<< MATCH' if v in recorded else ''))
