#!/usr/bin/env python3
"""Pulls every on-chain figure the report uses, for one quarter, and saves it under data/raw/.
Each step writes its own file and is skipped if that file already exists, so a rerun only fetches what is missing.

  python3 scripts/fetch.py            fetch everything for the quarter set in QUARTER below

Sources (public, no key needed):
  RPC       https://governors.mainnet.redbelly.network   Redbelly mainnet, chain ID 151. Balances at any block,
                                                         blocks with their transactions, contract logs and calls.
  Routescan https://api.routescan.io/v2/network/mainnet/evm/151/...
                                                         the explorer's list of addresses with a native balance and their
                                                         public labels, and internal (contract to address) RBNT transfers.

Steps
  1 blocks      the last block before the quarter starts and the last block of the quarter, found by block timestamp (UTC)
  2 labels      every address Routescan lists with an RBNT balance today, with its public name tag if it has one
  3 touched     every address that sent or received RBNT from the start of the quarter to today: from the transactions in
                every block (RPC) and from internal transfers (Routescan). With step 2 this covers every address that held RBNT
                at either date, because an address can only gain or lose RBNT by appearing in one of these.
  4 balances    the native RBNT balance of every address in steps 2 and 3, at both blocks (RPC eth_getBalance)
  5 wrbnt       every address Routescan lists as a WRBNT holder today, plus every address in a WRBNT log since the quarter
                started, and its WRBNT balance at both blocks (RPC eth_call)
  6 named       for each publicly named wallet: its transactions and internal transfers within the quarter (Routescan)
  7 staking     for the two Reddex RBNT staking pools: RBNT balance, totalStake() and lockPeriod() at both blocks, and every
                Stake, Unstake and reward claim event within the quarter (RPC eth_getLogs)
  8 stakers     every address that has ever called stake() on either pool (Routescan transaction list of the pool), and its
                staked amount at both blocks (RPC userInfo). The sum is checked against totalStake() in the analysis.
"""
import json, sys, time, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw"
RPC = "https://governors.mainnet.redbelly.network"
RS = "https://api.routescan.io"
RS_API = RS + "/v2/network/mainnet/evm/151/etherscan/api"
QUARTER = {"name": "Q3 2026", "start": "2026-07-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"}
WRBNT = "0x6ed1f491e2d31536d6561f6bdb2adc8f092a6076"
UA = {"User-Agent": "Mozilla/5.0 (holder report)"}
NAMED = json.loads((ROOT / "content/named_wallets.json").read_text())

def http(url, data=None, tries=14):
    for t in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={**UA, **({"content-type": "application/json"} if data else {})})
            return json.loads(urllib.request.urlopen(req, timeout=120).read())
        except Exception as e:
            if t == tries - 1:
                raise
            # Routescan answers 429 when the free limit is reached; wait longer each time
            time.sleep((10 if "429" in str(e) else 2) * (t + 1))

def routescan_rows(params):
    """All rows of an Etherscan-style Routescan query, page by page, slowly enough to stay under the free limit.
    The API stops at 10,000 rows per query, so a query that reaches that cap is split into two block ranges."""
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({**params, "page": page, "offset": 1000})
        d = http(f"{RS_API}?{q}")
        res = d.get("result") if isinstance(d.get("result"), list) else []
        rows += res
        if len(res) < 1000:
            return rows
        page += 1
        time.sleep(0.6)
        if page > 10:
            a, b = int(params["startblock"]), int(params["endblock"])
            if a >= b:
                raise SystemExit(f"more than 10,000 rows in one block: {params}")
            m = (a + b) // 2
            return routescan_rows({**params, "endblock": m}) + routescan_rows({**params, "startblock": m + 1})

def rpc_batch(calls, size=50):
    """calls: list of (method, params). Returns results in order. A rate limit answer is retried with a growing pause."""
    out = []
    for i in range(0, len(calls), size):
        chunk = calls[i:i + size]
        body = json.dumps([{"jsonrpc": "2.0", "id": k, "method": m, "params": p} for k, (m, p) in enumerate(chunk)]).encode()
        for attempt in range(8):
            res = sorted(http(RPC, body), key=lambda r: r["id"])
            errs = [r["error"] for r in res if "error" in r]
            if not errs:
                break
            if any("rate limit" in str(e) for e in errs):
                time.sleep(3 * (attempt + 1)); continue
            raise SystemExit(f"RPC error: {errs[0]}")
        else:
            raise SystemExit("RPC still rate limited after retries")
        out += [r["result"] for r in res]
    return out

def save(name, obj):
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(obj, indent=None if isinstance(obj, (list, dict)) and len(obj) > 50 else 1))

def have(name):
    return (RAW / name).exists()

def ts(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())

def get_logs(address, a, b, window=100):
    """eth_getLogs over [a, b]. The Redbelly RPC serves at most about 100 blocks per query and rate limits log filters,
    so the range is split and sent in small batches, one after another."""
    spans = [(s, min(s + window - 1, b)) for s in range(a, b + 1, window)]
    logs = []
    for i in range(0, len(spans), 10):
        res = rpc_batch([("eth_getLogs", [{"address": address, "fromBlock": hex(x), "toBlock": hex(y)}]) for x, y in spans[i:i + 10]], size=10)
        for r in res:
            logs += r
        time.sleep(0.2)
    return logs

# ---------- 1 boundary blocks ----------
def block_time(n):
    return int(rpc_batch([("eth_getBlockByNumber", [hex(n), False])])[0]["timestamp"], 16)

def last_block_before(t):
    lo, hi = 1, int(rpc_batch([("eth_blockNumber", [])])[0], 16)
    while lo < hi:   # largest block with timestamp < t
        mid = (lo + hi + 1) // 2
        if block_time(mid) < t:
            lo = mid
        else:
            hi = mid - 1
    return lo

def step_blocks():
    if have("blocks.json"):
        return json.loads((RAW / "blocks.json").read_text())
    s, e = last_block_before(ts(QUARTER["start"])), last_block_before(ts(QUARTER["end"]))
    head = int(rpc_batch([("eth_blockNumber", [])])[0], 16)
    out = {"quarter": QUARTER, "start_block": s, "end_block": e, "head_at_fetch": head,
           "start_block_time": block_time(s), "start_next_time": block_time(s + 1),
           "end_block_time": block_time(e), "end_next_time": block_time(e + 1),
           "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    save("blocks.json", out); print("blocks", out); return out

# ---------- 2 Routescan address list with labels ----------
def step_labels():
    if have("routescan_addresses.json"):
        return json.loads((RAW / "routescan_addresses.json").read_text())
    url, items = "/v2/network/mainnet/evm/151/addresses?sort=balance,desc&limit=200", []
    while url:
        d = http(RS + url); items += d.get("items", []); url = d.get("link", {}).get("next")
        if len(items) % 20000 == 0:
            print("addresses", len(items), flush=True)
    out = {"fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "items": [{"a": i["address"].lower(), "b": i["balance"], **({"name": i["name"]} if i.get("name") else {})} for i in items]}
    save("routescan_addresses.json", out); print("labels", len(items)); return out

# ---------- 3 every address touched since the quarter started ----------
def scan_range(a, b):
    found = set()
    blocks = rpc_batch([("eth_getBlockByNumber", [hex(n), True]) for n in range(a, b)])
    for blk in blocks:
        for tx in blk["transactions"]:
            found.add(tx["from"].lower())
            if tx.get("to"):
                found.add(tx["to"].lower())
    return found

def internal_range(a, b):
    found, page = set(), 1
    while True:
        q = urllib.parse.urlencode({"module": "account", "action": "txlistinternal", "startblock": a, "endblock": b, "page": page, "offset": 1000, "sort": "asc"})
        d = http(f"{RS_API}?{q}")
        res = d.get("result") if isinstance(d.get("result"), list) else []
        for r in res:
            if int(r["value"]) > 0 and r.get("type", "call") == "call":   # a delegatecall moves no RBNT
                found.add(r["from"].lower()); found.add(r["to"].lower())
        if len(res) < 1000:
            return found, False
        page += 1
        if page > 10:   # the API serves at most 10,000 rows per query; the caller splits the range
            return found, True

def step_burn(blocks):
    """Base fees are burned (EIP-1559), so total supply falls a little with every block. Sums base fee x gas used
    for every block inside the quarter, to check that the fall in the total of all balances matches it."""
    if have("burn.json"):
        return json.loads((RAW / "burn.json").read_text())
    a, b = blocks["start_block"] + 1, blocks["end_block"]
    ranges = [(n, min(n + 100, b + 1)) for n in range(a, b + 1, 100)]
    def burned(r):
        hs = rpc_batch([("eth_getBlockByNumber", [hex(n), False]) for n in range(*r)])
        return sum(int(h.get("baseFeePerGas", "0x0"), 16) * int(h["gasUsed"], 16) for h in hs), len(hs)
    total = n = 0
    with ThreadPoolExecutor(4) as ex:
        for s, k in ex.map(burned, ranges):
            total += s; n += k
    out = {"from_block": a, "to_block": b, "blocks": n, "burned_wei": str(total)}
    save("burn.json", out); print("burned", total / 1e18); return out

def step_touched(blocks):
    if have("touched.json"):
        return set(json.loads((RAW / "touched.json").read_text())["addresses"])
    start, head = blocks["start_block"] + 1, blocks["head_at_fetch"]
    found, ranges = set(), [(n, min(n + 500, head + 1)) for n in range(start, head + 1, 500)]
    if have("touched_tx.json"):
        found = set(json.loads((RAW / "touched_tx.json").read_text()))
    else:
        with ThreadPoolExecutor(6) as ex:
            for i, s in enumerate(ex.map(lambda r: scan_range(*r), ranges)):
                found |= s
                if i % 40 == 0:
                    print("blocks scanned", ranges[i][1], len(found), flush=True)
        save("touched_tx.json", sorted(found))
    n_tx = len(found)
    def internal(a, b):
        f, more = internal_range(a, b)
        if more and b - a > 1:
            m = (a + b) // 2
            return internal(a, m) | internal(m + 1, b)
        return f
    for a in range(start, head + 1, 5000):
        found |= internal(a, min(a + 4999, head))
    save("touched.json", {"from_block": start, "to_block": head, "addresses_from_transactions": n_tx, "addresses": sorted(found)})
    print("touched", len(found)); return found

# ---------- 4 balances at both blocks ----------
def step_balances(blocks, addrs):
    """Native RBNT of every address at both blocks, read from the chain. Resumable: finished chunks are kept in
    balances.partial.json, so an interrupted run carries on where it stopped."""
    if have("balances.json"):
        return json.loads((RAW / "balances.json").read_text())
    part = RAW / "balances.partial.json"
    out = json.loads(part.read_text()) if part.exists() else {"start": {}, "end": {}, "queried": []}
    done = set(out["queried"])
    todo = sorted(set(addrs) - done)
    chunks = [todo[i:i + 500] for i in range(0, len(todo), 500)]
    def get(ch):
        res = {}
        for tag, b in (("start", blocks["start_block"]), ("end", blocks["end_block"])):
            res[tag] = dict(zip(ch, (int(x, 16) for x in rpc_batch([("eth_getBalance", [a, hex(b)]) for a in ch]))))
        return ch, res
    with ThreadPoolExecutor(6) as ex:
        for i, (ch, res) in enumerate(ex.map(get, chunks)):
            for tag in ("start", "end"):
                out[tag].update({a: str(v) for a, v in res[tag].items() if v > 0})
            out["queried"] += ch
            if i % 40 == 39:
                part.write_text(json.dumps(out)); print("balances", len(out["queried"]), flush=True)
    out["queried"] = sorted(set(out["queried"]))
    save("balances.json", out); part.unlink(missing_ok=True); return out

# ---------- 5 Wrapped RBNT ----------
def step_wrbnt(blocks):
    if have("wrbnt.json"):
        return json.loads((RAW / "wrbnt.json").read_text())
    head = blocks["head_at_fetch"]
    # holders today (Routescan) plus every address in a WRBNT log since the quarter started: together these cover every
    # address that held WRBNT at either date, for the same reason as in step 3
    url, current = f"/v2/network/mainnet/evm/151/erc20/{WRBNT}/holders?limit=200", []
    while url:
        d = http(RS + url); current += [i["address"].lower() for i in d.get("items", [])]; url = d.get("link", {}).get("next")
    logs = get_logs(WRBNT, blocks["start_block"] + 1, head)
    holders = set(current)
    for lg in logs:
        for tpc in lg["topics"][1:]:
            holders.add("0x" + tpc[-40:].lower())
    holders = sorted(holders)
    out = {"current_holders_listed": len(current), "logs_since_start": len(logs), "holders_checked": len(holders)}
    for tag, b in (("start", blocks["start_block"]), ("end", blocks["end_block"])):
        vals = rpc_batch([("eth_call", [{"to": WRBNT, "data": "0x70a08231" + "0" * 24 + h[2:]}, hex(b)]) for h in holders])
        out[tag] = {h: str(int(v, 16)) for h, v in zip(holders, vals) if v not in ("0x", "0x0") and int(v, 16) > 0}
        out[tag + "_supply"] = str(int(rpc_batch([("eth_call", [{"to": WRBNT, "data": "0x18160ddd"}, hex(b)])])[0], 16))
    save("wrbnt.json", out); print("wrbnt", len(logs), len(holders)); return out

# ---------- 6 flows of the publicly named wallets ----------
def step_named(blocks):
    if have("named_flows.json"):
        return
    out = {}
    for w in NAMED:
        a = w["address"].lower(); rows = {}
        for action in ("txlist", "txlistinternal"):
            got = routescan_rows({"module": "account", "action": action, "address": a, "startblock": blocks["start_block"] + 1,
                                  "endblock": blocks["end_block"], "sort": "asc"})
            rows[action] = [{"block": r["blockNumber"], "hash": r["hash"], "from": r["from"].lower(), "to": (r.get("to") or "").lower(),
                             "value": r["value"], "isError": r.get("isError", "0"), "gasUsed": r.get("gasUsed", "0"), "gasPrice": r.get("gasPrice", "0"),
                             **({"type": r.get("type", "call")} if action == "txlistinternal" else {})} for r in got]
            time.sleep(0.6)
        out[a] = rows
        print("named", w["name"], {k: len(v) for k, v in rows.items()}, flush=True)
    save("named_flows.json", out)

# ---------- 7 Reddex staking pools ----------
def keccak(text):
    from Crypto.Hash import keccak as k
    h = k.new(digest_bits=256); h.update(text.encode()); return h.hexdigest()

POOL_EVENTS = {"Stake": "Stake(address,uint256,uint256,uint256)", "Unstake": "Unstake(address,uint256,uint256,uint256)",
               "Claim": "ClaimLiquidXReward(address,uint256)"}

def step_staking(blocks):
    if have("staking.json"):
        return json.loads((RAW / "staking.json").read_text())
    topics = {"0x" + keccak(sig): name for name, sig in POOL_EVENTS.items()}
    out = {}
    for w in (w for w in NAMED if w["group"] == "staking"):
        a = w["address"].lower(); d = {}
        for tag, b in (("start", blocks["start_block"]), ("end", blocks["end_block"])):
            bal, stake, lock = rpc_batch([("eth_getBalance", [a, hex(b)]),
                                          ("eth_call", [{"to": a, "data": "0x" + keccak("totalStake()")[:8]}, hex(b)]),
                                          ("eth_call", [{"to": a, "data": "0x" + keccak("lockPeriod()")[:8]}, hex(b)])])
            d[tag] = {"balance": str(int(bal, 16)), "totalStake": str(int(stake, 16)), "lockPeriod_seconds": int(lock, 16)}
        logs = get_logs(a, blocks["start_block"] + 1, blocks["end_block"])
        ev = []
        for lg in logs:
            name = topics.get(lg["topics"][0])
            if name:
                data = lg["data"][2:]
                ev.append({"event": name, "block": int(lg["blockNumber"], 16), "account": "0x" + data[24:64], "amount": str(int(data[64:128], 16))})
        d["events"] = ev
        out[a] = d
        print("staking", w["name"], {k: sum(1 for e in ev if e["event"] == k) for k in POOL_EVENTS}, flush=True)
    save("staking.json", out); return out

# ---------- 8 stakers and their staked amounts ----------
def step_stakers(blocks):
    if have("stakers.json"):
        return json.loads((RAW / "stakers.json").read_text())
    stake_sel = "0x" + keccak("stake()")[:8]
    user_sel = "0x" + keccak("userInfo(address)")[:8]
    staking = json.loads((RAW / "staking.json").read_text()) if have("staking.json") else {}
    out = {}
    for w in (w for w in NAMED if w["group"] == "staking"):
        a = w["address"].lower()
        txs = routescan_rows({"module": "account", "action": "txlist", "address": a, "startblock": 0, "endblock": blocks["head_at_fetch"], "sort": "asc"})
        stakers = {r["from"].lower() for r in txs if r.get("input", "").startswith(stake_sel)}
        stakers |= {e["account"] for e in staking.get(a, {}).get("events", [])}
        stakers = sorted(stakers)
        d = {"pool_transactions": len(txs), "stakers_seen": len(stakers)}
        for tag, b in (("start", blocks["start_block"]), ("end", blocks["end_block"])):
            vals = rpc_batch([("eth_call", [{"to": a, "data": user_sel + "0" * 24 + s[2:]}, hex(b)]) for s in stakers])
            d[tag] = {s: str(int(v[2:66], 16)) for s, v in zip(stakers, vals) if len(v) >= 66 and int(v[2:66], 16) > 0}
        out[a] = d
        print("stakers", w["name"], len(txs), len(stakers), flush=True)
    save("stakers.json", out); return out

def wei(s):
    """Routescan sometimes writes round balances in exponent form ("2E+27"); Decimal keeps them exact."""
    from decimal import Decimal
    return int(Decimal(s))

def step_listing_check(blocks, labels, bal):
    """How far the explorer's balance list (today) is from the chain, for addresses that have not moved since the
    quarter began. Recorded so the method can say why every balance in the report is read from the chain."""
    if have("listing_check.json"):
        return json.loads((RAW / "listing_check.json").read_text())
    touched = set(json.loads((RAW / "touched.json").read_text())["addresses"])
    exact = rounded = wrong = 0
    for i in labels["items"]:
        if i["a"] in touched:
            continue
        chain, listed = int(bal["end"].get(i["a"], 0)), wei(i["b"])
        if chain == listed:
            exact += 1
        elif chain and abs(chain - listed) <= chain // 10 ** 12:
            rounded += 1
        else:
            wrong += 1
    out = {"unmoved_addresses_compared": exact + rounded + wrong, "exact": exact, "rounded_in_listing": rounded, "different": wrong}
    save("listing_check.json", out); print(out); return out

def step_code(blocks, addrs):
    """Whether each address with a balance is a contract (has code at the end block) or a plain wallet. An on-chain
    fact about the address, used only to split the groups; it says nothing about who controls it."""
    if have("code.json"):
        return json.loads((RAW / "code.json").read_text())
    addrs = sorted(addrs)
    got = rpc_batch([("eth_getCode", [a, hex(blocks["end_block"])]) for a in addrs])
    out = {"block": blocks["end_block"], "contracts": sorted(a for a, c in zip(addrs, got) if c not in ("0x", "0x0", None))}
    save("code.json", out); print("contracts", len(out["contracts"])); return out

def main():
    blocks = step_blocks()
    labels = step_labels()
    touched = step_touched(blocks)
    # Every address the explorer lists, every address active since the quarter began, and the named wallets.
    # Balances come from the chain, never from the list: the list rounds large balances and can be out of date.
    universe = {i["a"] for i in labels["items"]} | touched | {w["address"].lower() for w in NAMED}
    bal = step_balances(blocks, universe)
    step_burn(blocks)
    step_listing_check(blocks, labels, bal)
    step_wrbnt(blocks)
    step_named(blocks)
    step_staking(blocks)
    stakers = step_stakers(blocks)
    held = set(bal["start"]) | set(bal["end"]) | set(json.loads((RAW / "wrbnt.json").read_text())["start"]) \
        | set(json.loads((RAW / "wrbnt.json").read_text())["end"]) | {a for p in stakers.values() for t in ("start", "end") for a in p[t]}
    step_code(blocks, held)
    print("done")

if __name__ == "__main__":
    main()
