from math import comb
def fisher_one_sided(a,b,c,d):
    # 表: [a b; c d]，检验 a/n1 > c/n2 的单侧 p
    n1=a+b; n2=c+d; K=a+c; N=n1+n2
    p=0.0
    for x in range(a, min(n1,K)+1):
        p += comb(K,x)*comb(N-K,n1-x)/comb(N,n1)
    return p
