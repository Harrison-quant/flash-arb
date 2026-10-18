"""Check 2 diagnosis: replay each August swap two ways and count exact (input, output, end price) matches.

1. Free: exact-input of the amount the pool received, no price limit (the original Check 2).
2. Limited: the same, with the event's post-swap sqrt price as the price limit.
A swap that stopped at a limit, or was exact-output, overshoots in replay 1 but is reproduced by 2.
"""
from scan_august import *
pools = initial_pools()
S = {p: dict(n=0, free=0, lim=0, either=0, in1=0, other=[] ) for p in POOLS}
for tx in transactions():
    for e in tx:
        pool = pools[e["pool"]]
        if e["event"] == "swap":
            a0, a1 = int(e["amount0"]), int(e["amount1"])
            zfo = a0 > 0
            amt, outw = (a0, -a1) if zfo else (a1, -a0)
            if amt > 0:
                s = S[e["pool"]]; s["n"] += 1; want = int(e["sqrtp"])
                u1, o1, p1 = pool.swap(zfo, amt)
                u2, o2, p2 = pool.swap(zfo, amt, limit=want)
                f = (u1, o1, p1) == (amt, outw, want); l = (u2, o2, p2) == (amt, outw, want)
                s["free"] += f; s["lim"] += l; s["either"] += f or l
                if not (f or l):
                    if o2 == outw and p2 == want and amt - u2 == 1: s["in1"] += 1
                    elif len(s["other"]) < 3: s["other"].append((e["block"], e["log_index"], amt - u2, o2 - outw, p2 - want, o1 - outw))
        apply(pool, e)
tot = {k: 0 for k in ("n", "either", "in1")}
for p in POOLS:
    s = S[p]
    for k in tot: tot[k] += s[k]
    print(f"{LABEL[p]:28s} n={s['n']:7d} free_exact={s['free']/s['n']:.4f} limit_exact={s['lim']/s['n']:.4f} "
          f"either={s['either']/s['n']:.5f} input_off_by_1wei={s['in1']} other={s['n']-s['either']-s['in1']} {s['other']}")
print(tot)
