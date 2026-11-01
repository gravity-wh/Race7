import io, os, hashlib
base = os.path.expanduser('~/Huangcw/presubmission_eda260769')
bad = ok = 0
for ln in io.open(base + '/MANIFEST.txt', encoding='utf-8'):
    ln = ln.rstrip('\n')
    if not ln or ln.startswith('#'):
        continue
    h, _, p = ln.partition('  ')
    fp = os.path.join(base, p)
    if not os.path.exists(fp):
        print('MISSING', p); bad += 1; continue
    d = hashlib.sha256(io.open(fp, 'rb').read()).hexdigest()
    if d != h:
        print('MISMATCH', p); bad += 1
    else:
        ok += 1
print('OK=%d BAD=%d' % (ok, bad))
