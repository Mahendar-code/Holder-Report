# Method and sources

How the RBNT holder report is produced, written so that someone else can produce the next edition. Every step reads public data, and the scripts in `scripts/` do every step.

## 1. Fix the two moments

A quarter is compared at two moments: the end of the day before the quarter starts and the end of its last day. Each moment is the last block before midnight UTC.

`fetch.py` finds them with a binary search on block timestamps (`eth_getBlockByNumber`) and records the block number, its time and the time of the next block in `data/raw/blocks.json`, so anyone can confirm the next block is after midnight.

For Q3 2026:

| Moment | Block | Block time (UTC) | Next block (UTC) |
|---|---|---|---|
| Start, end of 30 June 2026 | 3,025,809 | 2026-06-30 23:57:19 | 2026-07-01 00:02:18 |
| End, end of 30 September 2026 | 3,209,414 | 2026-09-30 23:57:35 | 2026-10-01 00:00:24 |

## 2. Find every address that matters

The universe is the union of three sets:

1. **Every address in Routescan's address list.** This is `GET https://api.routescan.io/v2/network/mainnet/evm/151/addresses?sort=balance,desc&limit=200`, followed page by page through `link.next`. The list is used only to find addresses and to read the public `name` Routescan gives some of them. For this edition Routescan reported about 742,742 addresses; the free API served the list in balance order down to addresses it shows with 5 RBNT (595,000 addresses) before its rate limit stopped further pages. Addresses further down show 5 RBNT or less in the list, so they can only touch the two smallest size bands, and any of them active during the quarter is in set 2 below. A later run with more time between requests, or with a Routescan API key, reads the full list.
2. **Every address active since the start block.**
   - Every `from` and `to` of every transaction in every block from the start block plus one to the chain head (`eth_getBlockByNumber` with full transactions).
   - Every party to an internal transfer with a value above zero in the same blocks, of type `call`. This comes from Routescan's `module=account&action=txlistinternal&startblock=..&endblock=..`. The script splits a range in half whenever it reaches the API's 10,000 row limit.
3. **The named wallets** in `content/named_wallets.json`.

## 3. Read balances from the chain

`eth_getBalance(address, block)` on `https://governors.mainnet.redbelly.network` (chain ID 151), for every address in the universe, at both blocks. Balances are never taken from the explorer list. On this edition's fetch date the list rounded large balances and showed some addresses with a balance the chain did not have at either block.

`fetch.py` records how often the list and the chain disagree, in `data/raw/listing_check.json` (also in `figures.json`). For this edition, of 594,053 listed addresses that did not move during the quarter, the list matched the chain exactly for 13,184, was rounded for 12,735 and was different for 568,134, most of them shown with a balance the chain has as zero.

## 4. Wrapped RBNT (WRBNT)

Contract `0x6ed1f491e2d31536d6561f6bdb2adc8f092a6076`.

- **Holders:** Routescan's holder list (`/v2/network/mainnet/evm/151/erc20/<contract>/holders`), plus every address in a `Transfer` event since the start block (`eth_getLogs`, 100 blocks per call).
- **Reads at both blocks:** `balanceOf(address)` (selector `0x70a08231`) for every holder, and `totalSupply()` (selector `0x18160ddd`).
- **Check:** the total supply must equal the RBNT the contract holds, and the sum of all balances.

## 5. The two Reddex pools

| Pool | Address | Lock |
|---|---|---|
| No lock | `0x43A1dc107BBb06dF266278056055AE7Fc5bd2817` | 0 days |
| 365 day | `0x5E8040e85D0E6363D798a43BEa939C026449946d` | 365 days |

Both run the verified contract `ReddexRBNTLockStaker`; the source is published on Routescan and its SHA-256 is in `evidence/manifest.json`.

At both blocks:

- `eth_getBalance` of the pool.
- `totalStake()` (selector `0x8b0e9f3f`).
- `lockPeriod()` (selector `0x3fd8b02f`).
- `userInfo(address)` for every address that ever staked. Its first word is the staked amount. The stakers are found from every transaction to the pool whose input starts with the `stake()` selector, plus every Stake and Unstake event.

During the quarter, the script reads the `Stake`, `Unstake` and `ClaimLiquidXReward` events.

**Pool balances include reward funds.** Rewards are paid in RBNT from the pool's own balance (`_claim` pays out of `address(this).balance - totalStake`). A pool's balance therefore may include reward funds as well as stakes, so staking is measured with `totalStake` and the stakers' own amounts. The rest of the balance is shown as reward funds.

Checks:

- the stakers' amounts must add up to `totalStake` at both blocks
- Stake minus Unstake in the quarter must equal the change in `totalStake`

## 6. Positions: counting every RBNT once

The **position** of an address = native RBNT + WRBNT + RBNT staked in either pool.

The WRBNT contract is left out, because its RBNT is counted with whoever holds the WRBNT. Each pool keeps only its balance minus `totalStake` (reward funds), because the staked RBNT is counted with the stakers.

Section 1 of the report is the one exception. It shows where RBNT physically sits, so the WRBNT contract and the pools appear there as places, each counted once.

## 7. Groups, never individuals

Named wallets are reported by name. They are:

- the nine reserved wallets in the table on https://redbellydao.network/treasury/ (read from the page's script; its address and SHA-256 are in `evidence/manifest.json`)
- the WRBNT contract
- the two pools
- any address Routescan gives a public name

A Routescan name that contains an exchange name or the word "exchange" marks a labelled exchange wallet. On this edition's fetch date, Routescan named one address on Redbelly mainnet, the WRBNT contract, and no exchange.

Every other address is a **community holder** and appears only in counts and totals:

- **Size bands:** under 1, 1 to 100, 100 to 1,000 and so on up to 100 million and over RBNT.
- **Rank groups** (largest 10, ranks 11 to 100, ranks 101 to 1,000), ranked by position at the start. A holder "added" if its position rose by more than 1% and "reduced" if it fell by more than 1%.
- **Contract or wallet**, from `eth_getCode` at the end block.

`analyse.py` stops if any reported band holds fewer than 5 addresses. No output file contains a community holder's address.

## 8. Flows of the named wallets

For each named wallet, the quarter's transactions come from Routescan's API: `txlist` and `txlistinternal` with `startblock` = start + 1 and `endblock` = end.

- Failed calls (`isError` = 1) are left out, and so are internal records that are not of type `call`. A delegate call repeats the value of its parent call without moving RBNT.
- Fees are gas used times gas price for every transaction the wallet sent.
- Counterparties are given by type only: a named wallet by name, otherwise "unlabelled wallets" or "unlabelled contracts".

**Check:** start balance + RBNT in − RBNT out − fees = end balance. The gap is in the `reconciliation gap` column of `06_named_wallets.csv` and must be zero.

## 9. Producing the next edition

```
# 1. in scripts/fetch.py set QUARTER = {"name": "Q4 2026", "start": "2026-10-01T00:00:00Z", "end": "2027-01-01T00:00:00Z"}
python3 scripts/fetch.py      # about two hours, mostly the explorer address list; resumable
python3 scripts/analyse.py    # writes data/*.csv and data/figures.json, prints the checks
python3 scripts/build.py      # writes the web page, PDF, Word file and the community summary
python3 scripts/check.py      # must end with RESULT: PASS
```

Text that describes a direction (rose, fell) is written in `scripts/build.py` next to the number it describes; read it once against the new figures before publishing.

## Sources

| Source | Address | Used for |
|---|---|---|
| Redbelly mainnet RPC, chain ID 151 | https://governors.mainnet.redbelly.network | All balances, WRBNT, pool reads, blocks, events, contract code |
| Routescan Etherscan-compatible API | https://api.routescan.io/v2/network/mainnet/evm/151/etherscan/api | Named wallet transactions, internal transfers, pool transactions, verified source |
| Routescan address list | https://api.routescan.io/v2/network/mainnet/evm/151/addresses | Finding addresses, public names |
| Routescan WRBNT holders | https://api.routescan.io/v2/network/mainnet/evm/151/erc20/0x6ed1f491e2d31536d6561f6bdb2adc8f092a6076/holders | Finding WRBNT holders |
| Redbelly DAO treasury page | https://redbellydao.network/treasury/ | Names, addresses and launch allocations of the reserved wallets |
| Reddex staking | https://www.reddex.io/stake | The two RBNT pools |

All data for this edition was read on 17 October 2026. Address-level raw files are kept out of the repository on purpose, because they would list community holders one by one. `scripts/fetch.py` recreates them from the public sources above.
