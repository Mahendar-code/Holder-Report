#!/usr/bin/env python3
"""Turns the raw on-chain data in data/raw/ into the tables and figures the report uses.

Writes every table as a CSV in data/ and every number the report quotes into data/figures.json.
No individual address is written to any output except the publicly named wallets: Redbelly's reserved wallets
from the DAO treasury page, the Wrapped RBNT contract, the two Reddex staking pools, and any address Routescan
names. Every other address is only counted inside a group, and no group of fewer than 5 holders is reported.

Two ways of looking at the same RBNT
1. Where the RBNT physically sits (table 01): the native RBNT balance of every address. The Wrapped RBNT
   contract and the staking pools appear as places, because that is where the coins are.
2. What each holder controls (tables 02 to 04), called the holder's "position":
     native RBNT in the address
   + Wrapped RBNT (WRBNT) held by the address   each WRBNT is backed one to one by RBNT inside the WRBNT contract,
                                                so the contract is left out and that RBNT is counted once, with
                                                whoever holds the WRBNT
   + RBNT the address has staked in either Reddex pool (the pool's userInfo amount for the address)
                                                the pools are left out for the staked RBNT, which is counted with
                                                the stakers; what is left in a pool (reward funds) stays with it
"""
import csv, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data/raw", ROOT / "data"
E18 = 10 ** 18
MIN_GROUP = 5
NAMED = json.loads((ROOT / "content/named_wallets.json").read_text())
NAMED_BY = {w["address"].lower(): w for w in NAMED}
WRBNT = "0x6ed1f491e2d31536d6561f6bdb2adc8f092a6076"
POOLS = [w["address"].lower() for w in NAMED if w["group"] == "staking"]
RESERVED = [w["address"].lower() for w in NAMED if w["group"] == "reserved"]
# Routescan name tags that mark an exchange wallet; any other Routescan name is a labelled contract or wallet
EXCHANGE_WORDS = ("exchange", "binance", "bybit", "okx", "kucoin", "gate.io", "mexc", "bitget", "htx", "huobi", "bitmart", "coinbase",
                  "kraken", "crypto.com", "lbank", "bitrue", "coinstore", "xt.com", "probit", "poloniex", "bingx", "hotcoin", "biconomy",
                  "independent reserve", "swyftx", "coinspot", "btc markets", "uphold", "digital surge", "bitstamp", "hot wallet")
BANDS = [("100 million and over", 1e8), ("10 million to 100 million", 1e7), ("1 million to 10 million", 1e6),
         ("100,000 to 1 million", 1e5), ("10,000 to 100,000", 1e4), ("1,000 to 10,000", 1e3), ("100 to 1,000", 1e2),
         ("1 to 100", 1), ("under 1", 0)]
COHORTS = [("largest 10", 0, 10), ("ranks 11 to 100", 10, 100), ("ranks 101 to 1,000", 100, 1000)]

def load(name):
    return json.loads((RAW / name).read_text())

def rbnt(wei):
    return int(wei) / E18

def r2(wei):
    return round(rbnt(wei), 2)

def write_csv(name, header, rows):
    with open(OUT / name, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)

def band_of(wei):
    x = rbnt(wei)
    for name, lo in BANDS:
        if x >= lo:
            return name

def main():
    blocks = load("blocks.json")
    listing = load("routescan_addresses.json")
    labels = {i["a"]: i["name"] for i in listing["items"] if i.get("name")}
    bal = load("balances.json")
    wr = load("wrbnt.json")
    stk = load("staking.json")
    stakers = load("stakers.json")
    flows = load("named_flows.json")
    burn = load("burn.json")
    contracts = set(load("code.json")["contracts"])
    fig = {"quarter": blocks["quarter"], "start_block": blocks["start_block"], "end_block": blocks["end_block"],
           "start_block_time": blocks["start_block_time"], "end_block_time": blocks["end_block_time"],
           "fetched_utc": blocks["fetched_utc"], "listing_fetched_utc": listing["fetched_utc"],
           "listing_count": len(listing["items"]), "listing_approx_total": listing.get("approx_total"),
           "listing_read_to_rbnt": listing.get("read_to_listed_balance_rbnt"), "read_from_chain": len(bal["queried"]),
           "listing_check": load("listing_check.json"),
           "labelled_on_routescan": {a: n for a, n in labels.items()}}

    def kind(a):
        if a in NAMED_BY:
            return NAMED_BY[a]["group"]                     # reserved, wrbnt, staking
        if a in labels:
            n = labels[a].lower()
            return "exchange" if any(w in n for w in EXCHANGE_WORDS) else "labelled"
        return "contract" if a in contracts else "wallet"

    native = {t: {a: int(v) for a, v in bal[t].items()} for t in ("start", "end")}
    stake = {p: {t: {a: int(v) for a, v in stakers[p][t].items()} for t in ("start", "end")} for p in POOLS}

    # ---------- positions ----------
    positions = {}
    for t in ("start", "end"):
        pos = defaultdict(int)
        for a, v in native[t].items():
            if a != WRBNT:                             # the RBNT behind WRBNT is counted with the WRBNT holders
                pos[a] += v
        for a, v in wr[t].items():
            pos[a] += int(v)
        for p in POOLS:
            pos[p] -= sum(stake[p][t].values())        # what stays with the pool is reward funds
            for a, v in stake[p][t].items():
                pos[a] += v
        positions[t] = {a: v for a, v in pos.items() if v > 0}
        fig[f"{t}_total_native"] = rbnt(sum(native[t].values()))
        fig[f"{t}_total_positions"] = rbnt(sum(positions[t].values()))
        fig[f"{t}_wrbnt_supply"] = rbnt(wr[t + "_supply"])
        fig[f"{t}_wrbnt_contract_rbnt"] = rbnt(native[t].get(WRBNT, 0))
        fig[f"{t}_wrbnt_held_by_holders"] = rbnt(sum(int(v) for v in wr[t].values()))
    fig["burned_in_quarter"] = rbnt(burn["burned_wei"])

    # ---------- 01 where the RBNT sits ----------
    def place(a):
        return {"reserved": "Redbelly reserved wallets", "wrbnt": "Wrapped RBNT contract (backs WRBNT one to one)",
                "staking": None, "exchange": "Labelled exchange wallets", "labelled": "Other addresses named on Routescan",
                "contract": "Other contracts", "wallet": "Other wallets"}[kind(a)]
    order = ["Redbelly reserved wallets", "Reddex pools: staked RBNT", "Reddex pools: reward funds", "Wrapped RBNT contract (backs WRBNT one to one)",
             "Labelled exchange wallets", "Other addresses named on Routescan", "Other contracts", "Other wallets"]
    where = {t: defaultdict(int) for t in ("start", "end")}
    count = {t: defaultdict(int) for t in ("start", "end")}
    for t in ("start", "end"):
        for a, v in native[t].items():
            pl = place(a)
            if pl is None:
                st = int(stk[a][t]["totalStake"])
                where[t]["Reddex pools: staked RBNT"] += st
                where[t]["Reddex pools: reward funds"] += v - st
                continue
            where[t][pl] += v
            if v >= E18:
                count[t][pl] += 1
    tot = {t: sum(where[t].values()) for t in ("start", "end")}
    rows = []
    for k in order:
        s, e = where["start"][k], where["end"][k]
        rows.append([k, r2(s), round(s / tot["start"] * 100, 2), r2(e), round(e / tot["end"] * 100, 2), r2(e - s),
                     count["start"].get(k, ""), count["end"].get(k, "")])
        fig.setdefault("where", {})[k] = {"start": rbnt(s), "end": rbnt(e), "start_pct": s / tot["start"] * 100, "end_pct": e / tot["end"] * 100}
    rows.append(["Total", r2(tot["start"]), 100, r2(tot["end"]), 100, r2(tot["end"] - tot["start"]), "", ""])
    write_csv("01_where_the_rbnt_sits.csv", ["place", "RBNT at start", "% at start", "RBNT at end", "% at end", "change",
                                            "addresses with 1+ RBNT at start", "at end"], rows)

    # ---------- 02 community holders by size ----------
    community = lambda a: kind(a) in ("contract", "wallet")
    com = {t: {a: v for a, v in positions[t].items() if community(a)} for t in ("start", "end")}
    rows = []
    for name, lo in BANDS:
        cs = [v for v in com["start"].values() if band_of(v) == name]
        ce = [v for v in com["end"].values() if band_of(v) == name]
        rows.append([name, len(cs), len(ce), len(ce) - len(cs), r2(sum(cs)), r2(sum(ce)), r2(sum(ce) - sum(cs))])
        fig.setdefault("bands", {})[name] = {"start": len(cs), "end": len(ce), "rbnt_start": rbnt(sum(cs)), "rbnt_end": rbnt(sum(ce))}
        assert min(len(cs), len(ce)) >= MIN_GROUP or (len(cs) == 0 and len(ce) == 0), f"band {name} has fewer than {MIN_GROUP} holders"
    write_csv("02_holders_by_size.csv", ["holding size (RBNT)", "holders at start", "holders at end", "change",
                                        "RBNT held at start", "RBNT held at end", "change"], rows)
    for t in ("start", "end"):
        fig[f"holders_{t}_1plus"] = sum(1 for v in com[t].values() if v >= E18)
        fig[f"holders_{t}_any"] = len(com[t])
        fig[f"community_{t}_rbnt"] = rbnt(sum(com[t].values()))
        fig[f"community_{t}_contracts_rbnt"] = rbnt(sum(v for a, v in com[t].items() if a in contracts))
        fig[f"community_{t}_contracts_1plus"] = sum(1 for a, v in com[t].items() if a in contracts and v >= E18)
    s1 = {a for a, v in com["start"].items() if v >= E18}; e1 = {a for a, v in com["end"].items() if v >= E18}
    fig["holders_new_1plus"], fig["holders_left_1plus"], fig["holders_both_1plus"] = len(e1 - s1), len(s1 - e1), len(s1 & e1)

    # ---------- 03 concentration ----------
    srt = {t: sorted(com[t].values(), reverse=True) for t in ("start", "end")}
    rows = []
    for n in (10, 100, 1000, 10000):
        sh_s = sum(srt["start"][:n]) / sum(srt["start"]) * 100
        sh_e = sum(srt["end"][:n]) / sum(srt["end"]) * 100
        rows.append([f"largest {n:,}", r2(sum(srt['start'][:n])), round(sh_s, 2), r2(sum(srt['end'][:n])), round(sh_e, 2), round(sh_e - sh_s, 2)])
        fig[f"top{n}_share_start"], fig[f"top{n}_share_end"] = sh_s, sh_e
    def gini(xs):
        xs = sorted(xs); n = len(xs); tot_ = sum(xs)
        return sum((2 * i - n + 1) * x for i, x in enumerate(xs)) / (n * tot_) if tot_ else 0
    g_s = gini([v for v in srt["start"] if v >= E18]); g_e = gini([v for v in srt["end"] if v >= E18])
    fig["gini_start"], fig["gini_end"] = g_s, g_e
    rows.append(["Gini coefficient of holders with 1+ RBNT (0 = all equal, 1 = one holder has everything)", "", round(g_s, 4), "", round(g_e, 4), round(g_e - g_s, 4)])
    write_csv("03_concentration.csv", ["group", "RBNT at start", "share of community holdings at start (%)", "RBNT at end",
                                       "share at end (%)", "change (percentage points)"], rows)

    # ---------- 04 what the largest holders did, ranked at the start ----------
    rank = sorted(((v, a) for a, v in com["start"].items()), reverse=True)
    rows = []
    for name, lo, hi in COHORTS:
        members = rank[lo:hi]
        up = flat = down = gone = 0; s_tot = e_tot = 0
        for v, a in members:
            e = com["end"].get(a, 0); s_tot += v; e_tot += e
            ch = (e - v) / v
            if e < E18:
                gone += 1
            elif ch > 0.01:
                up += 1
            elif ch < -0.01:
                down += 1
            else:
                flat += 1
        rows.append([name, len(members), up, flat, down, gone, r2(s_tot), r2(e_tot), r2(e_tot - s_tot), round((e_tot - s_tot) / s_tot * 100, 2)])
        fig.setdefault("cohorts", {})[name] = {"holders": len(members), "up": up, "flat": flat, "down": down, "gone": gone,
                                               "start": rbnt(s_tot), "end": rbnt(e_tot)}
    write_csv("04_largest_holders.csv", ["group (ranked by position at start)", "holders", "added more than 1%", "within 1%",
                                         "reduced more than 1%", "under 1 RBNT at end", "RBNT at start", "RBNT at end", "net change",
                                         "net change (%)"], rows)
    top100_end = {a for v, a in sorted(((v, a) for a, v in com["end"].items()), reverse=True)[:100]}
    fig["top100_entered"] = len(top100_end - {a for v, a in rank[:100]})

    # ---------- 05 staking pools ----------
    rows = []
    for w in (w for w in NAMED if w["group"] == "staking"):
        a = w["address"].lower(); d = stk[a]; ev = d["events"]
        total = lambda k: sum(int(e["amount"]) for e in ev if e["event"] == k)
        who = lambda k: len({e["account"] for e in ev if e["event"] == k})
        n = lambda k: sum(1 for e in ev if e["event"] == k)
        st_s, st_e = int(d["start"]["totalStake"]), int(d["end"]["totalStake"])
        row = [w["name"], a, d["start"]["lockPeriod_seconds"] // 86400, r2(d["start"]["balance"]), r2(d["end"]["balance"]),
               r2(st_s), r2(st_e), r2(st_e - st_s), round((st_e - st_s) / st_s * 100, 2),
               sum(1 for v in stake[a]["start"].values() if v > 0), sum(1 for v in stake[a]["end"].values() if v > 0),
               n("Stake"), who("Stake"), r2(total("Stake")), n("Unstake"), who("Unstake"), r2(total("Unstake")),
               n("Claim"), who("Claim"), r2(total("Claim")),
               r2(int(d["start"]["balance"]) - st_s), r2(int(d["end"]["balance"]) - st_e)]
        rows.append(row)
        fig.setdefault("pools", {})[a] = dict(zip(["name", "address", "lock_days", "bal_start", "bal_end", "stake_start", "stake_end",
                                                   "stake_change", "stake_change_pct", "stakers_start", "stakers_end", "stake_tx",
                                                   "stake_accounts", "staked", "unstake_tx", "unstake_accounts", "unstaked",
                                                   "claim_tx", "claim_accounts", "claimed", "rest_start", "rest_end"], row))
        assert abs(total("Stake") - total("Unstake") - (st_e - st_s)) < E18, "pool events do not add up to the change in totalStake"
    write_csv("05_staking_pools.csv", ["pool", "address", "lock (days)", "RBNT balance at start", "RBNT balance at end",
                                       "staked (totalStake) at start", "staked at end", "change in staked", "change in staked (%)",
                                       "stakers at start", "stakers at end", "stake transactions", "addresses that staked", "RBNT staked",
                                       "unstake transactions", "addresses that unstaked", "RBNT unstaked", "reward claims",
                                       "addresses that claimed", "RBNT claimed", "balance minus staked at start", "at end"], rows)
    for t in ("start", "end"):
        fig[f"staked_total_{t}"] = rbnt(sum(int(stk[p][t]["totalStake"]) for p in POOLS))
        fig[f"stakers_unique_{t}"] = len({a for p in POOLS for a, v in stake[p][t].items() if v > 0})
        fig[f"staked_share_of_community_{t}"] = fig[f"staked_total_{t}"] / fig[f"community_{t}_rbnt"] * 100

    # ---------- 06 named wallets: balances and flows ----------
    def ctype(a):
        k = kind(a)
        if k in ("reserved", "wrbnt", "staking"):
            return NAMED_BY[a]["name"]
        return {"exchange": "a labelled exchange", "labelled": "an address named on Routescan",
                "contract": "unlabelled contracts", "wallet": "unlabelled wallets"}[k]
    rows, moves = [], []
    for w in NAMED:
        a = w["address"].lower()
        s, e = native["start"].get(a, 0), native["end"].get(a, 0)
        f = flows.get(a, {"txlist": [], "txlistinternal": []})
        inflow = outflow = fees = 0; n_in = n_out = 0
        peers = defaultdict(lambda: [0, 0, 0, 0])      # counterparty -> [in, out, transfers in, transfers out]
        for r, is_tx in [(r, True) for r in f["txlist"]] + [(r, False) for r in f["txlistinternal"]]:
            if is_tx and r["from"] == a:
                fees += int(r.get("gasUsed", 0)) * int(r.get("gasPrice", 0))   # the sender pays gas even if the call fails
            if r.get("isError") == "1" or r.get("type", "call") != "call":
                continue                               # failed calls and delegatecalls move no RBNT
            v = int(r["value"])
            if v == 0:
                continue
            if r["to"] == a:
                inflow += v; n_in += 1; p = peers[ctype(r["from"])]; p[0] += v; p[2] += 1
            if r["from"] == a:
                outflow += v; n_out += 1; p = peers[ctype(r["to"])]; p[1] += v; p[3] += 1
        recon = s + inflow - outflow - fees - e
        rows.append([w["name"], w["group"], a, r2(s), r2(e), r2(e - s), n_in, r2(inflow), n_out, r2(outflow), round(rbnt(fees), 6), round(rbnt(recon), 6)])
        fig.setdefault("named", {})[a] = {"name": w["name"], "group": w["group"], "start": rbnt(s), "end": rbnt(e), "in": rbnt(inflow),
                                          "out": rbnt(outflow), "n_in": n_in, "n_out": n_out, "fees": rbnt(fees), "recon": rbnt(recon)}
        if w["group"] == "reserved":
            for peer, (vi, vo, ni, no) in sorted(peers.items()):
                moves.append([w["name"], peer, ni, r2(vi), no, r2(vo)])
    for a in sorted(set(native["start"]) | set(native["end"])):
        if kind(a) == "exchange":
            s, e = native["start"].get(a, 0), native["end"].get(a, 0)
            rows.append([labels[a], "exchange (Routescan label)", a, r2(s), r2(e), r2(e - s), "", "", "", "", "", ""])
    write_csv("06_named_wallets.csv", ["wallet", "group", "address", "native RBNT at start", "native RBNT at end", "change", "transfers in",
                                      "RBNT in", "transfers out", "RBNT out", "fees paid (RBNT)", "reconciliation gap (RBNT)"], rows)
    write_csv("07_reserved_wallet_transfers.csv", ["reserved wallet", "counterparty", "transfers in", "RBNT in", "transfers out", "RBNT out"], moves)
    fig["reserved_start"] = rbnt(sum(native["start"].get(a, 0) for a in RESERVED))
    fig["reserved_end"] = rbnt(sum(native["end"].get(a, 0) for a in RESERVED))
    fig["exchanges_labelled"] = sum(1 for a in labels if kind(a) == "exchange")
    for t in ("start", "end"):
        fig[f"reserved_wrbnt_{t}"] = rbnt(sum(int(wr[t].get(a, 0)) for a in RESERVED))
        fig[f"reserved_staked_{t}"] = rbnt(sum(stake[p][t].get(a, 0) for p in POOLS for a in RESERVED))

    # ---------- checks that the data adds up ----------
    checks = {
        "WRBNT supply minus RBNT held by the WRBNT contract, start": fig["start_wrbnt_supply"] - fig["start_wrbnt_contract_rbnt"],
        "WRBNT supply minus RBNT held by the WRBNT contract, end": fig["end_wrbnt_supply"] - fig["end_wrbnt_contract_rbnt"],
        "WRBNT supply minus WRBNT found with holders, start": fig["start_wrbnt_supply"] - fig["start_wrbnt_held_by_holders"],
        "WRBNT supply minus WRBNT found with holders, end": fig["end_wrbnt_supply"] - fig["end_wrbnt_held_by_holders"],
        "positions total minus native total, start": fig["start_total_positions"] - fig["start_total_native"],
        "positions total minus native total, end": fig["end_total_positions"] - fig["end_total_native"],
    }
    for p in POOLS:
        for t in ("start", "end"):
            checks[f"pool {p[:6]} totalStake minus sum of stakers, {t}"] = rbnt(int(stk[p][t]["totalStake"]) - sum(stake[p][t].values()))
    for a, d in fig["named"].items():
        checks[f"reconciliation gap, {d['name']}"] = d["recon"]
    fig["checks"] = checks
    (OUT / "figures.json").write_text(json.dumps(fig, indent=1))
    for k, v in checks.items():
        print(f"{k}: {v:,.6f}")

if __name__ == "__main__":
    main()
