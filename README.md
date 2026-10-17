# RBNT holder report, Q3 2026

Live site: https://redbelly-onchain-holder.vercel.app

This report is a plain language, sourced account of how RBNT holders behaved between 1 July and 30 September 2026, read straight from the Redbelly chain. It covers:

- how holdings are spread and how concentrated they are
- what the largest holders did, in groups
- staking in the two Reddex pools
- the publicly named wallets

It describes trends, not people. It names only wallets that are already public:

- Redbelly's nine reserved wallets from the DAO treasury page
- the Wrapped RBNT contract
- the two Reddex staking pools
- any address Routescan labels

Every other address is counted only inside a group. It is not financial advice and makes no forecast of price.

## Deliverables

| Deliverable | Where |
|---|---|
| The report with charts, as PDF and Word | `public/downloads/rbnt-holder-report-q3-2026.pdf` and `.docx`, linked from every page of the site |
| The report as a web page | https://redbelly-onchain-holder.vercel.app (built into `public/`) |
| Community summary: four paragraphs and a 6 post X thread | `COMMUNITY-SUMMARY.md` and https://redbelly-onchain-holder.vercel.app/summary (with copy buttons) |
| The data behind every chart and table | `data/*.csv` and `data/figures.json`, also served at `/data/` |
| Method and sources note | `METHOD.md`, and sections 7 and 8 of the report |

## The data files

| File | What it holds |
|---|---|
| `01_where_the_rbnt_sits.csv` | RBNT by kind of address at both dates: reserved wallets, pools (staked and reward funds), WRBNT contract, other contracts, other wallets |
| `02_holders_by_size.csv` | Community holders and the RBNT they hold, by size band, at both dates |
| `03_concentration.csv` | Share held by the largest 10, 100, 1,000 and 10,000 community holders, and the Gini coefficient |
| `04_largest_holders.csv` | Holders ranked at the start, in three rank groups: how many added, held, reduced or left |
| `05_staking_pools.csv` | Each pool's balance, totalStake, stakers, stakes, unstakes and reward claims |
| `06_named_wallets.csv` | Each named wallet's balance at both dates, transfers in and out, fees and the reconciliation gap (zero for all) |
| `07_reserved_wallet_transfers.csv` | Each reserved wallet's transfers by counterparty type |
| `figures.json` | Every number quoted in the text, the two blocks and their times, and the results of every data check |

Every figure is a balance or event on Redbelly mainnet (chain ID 151) at one of two blocks:

| Block | Time (UTC) |
|---|---|
| 3,025,809 | 30 June 2026, 23:57:19 |
| 3,209,414 | 30 September 2026, 23:57:35 |

Events between the two blocks are also used. The data was read on 17 October 2026.

## How it is made

| Path | What it does |
|---|---|
| `scripts/fetch.py` | Reads the public data into `data/raw/`. Every step is resumable and skipped if its file exists |
| `scripts/analyse.py` | Builds positions (native RBNT + WRBNT + staked RBNT, each RBNT counted once), the groups and every table. It stops if a check fails or a group has fewer than 5 holders |
| `scripts/charts.py` | The SVG charts, in the Task Board palette |
| `scripts/build.py` | Writes the web page, the PDF, the Word file and `COMMUNITY-SUMMARY.md`, reading every number from `data/` |
| `scripts/check.py` | The quality gate, below |
| `content/named_wallets.json` | The twelve named addresses and where each name comes from |
| `content/treasury_allocations.json` | The launch allocations from the treasury page table |
| `evidence/manifest.json` | The address and SHA-256 of the treasury page script the reserved wallets were read from, and of the verified source code of both pools |

`data/raw/` is kept out of the repository on purpose. It lists community holders address by address, and the report never does. `scripts/fetch.py` recreates it from public sources in about two hours.

## Check it

```
python3 scripts/check.py            # must end with RESULT: PASS
python3 scripts/check.py --online   # also re-reads the named wallets and pools from the Redbelly RPC
```

`check.py` fails if:

- any data check is not zero:
  - WRBNT supply against the RBNT in the contract and against all WRBNT balances
  - each pool's stakers against its totalStake
  - each named wallet's reconciliation
- any output contains an address other than a named one
- a size band or rank group has fewer than 5 holders
- the text uses advice, forecast or hype words, an en or em dash, or an emoji
- the report does not say it is not financial advice, that a pool balance may include reward funds, or that WRBNT is counted once
- any deliverable contains a name, handle or link from the local, git-ignored `.credit-names` and `.credit-links` files, or the Word file names a tool or a person in its properties
- an X post is over 280 characters
- a number in the key findings is missing from the web page, the PDF or the Word file
- the web page loads anything from another domain, or a link points nowhere
- the published data differs from the analysis output

## Rebuild and preview

```
pip install playwright python-docx pycryptodome
python3 -m playwright install chromium
python3 scripts/fetch.py && python3 scripts/analyse.py && python3 scripts/build.py && python3 scripts/check.py
python3 -m http.server 8000 -d public          # then open http://localhost:8000
```

To produce the next edition, change `QUARTER` in `scripts/fetch.py` and run the same four commands. `METHOD.md` lists every call.

## Deploy

The site is static. `vercel.json` sets `public/` as the web root with no build step and turns on clean addresses, so `/summary` serves `public/summary.html`.

## Licences

- Fonts: Be Vietnam Pro and JetBrains Mono, SIL Open Font License 1.1 (`licenses/`).
- Logo and icon: the Redbelly DAO logo and the Task Board icon, from the Task Board brand kit.
- No third-party images are used.
