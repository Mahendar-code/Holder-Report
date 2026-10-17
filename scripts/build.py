#!/usr/bin/env python3
"""Builds every deliverable from data/figures.json and the CSV tables in data/:
  public/index.html            the report as a web page (one page, contents rail, charts with their data tables)
  public/summary.html          served at /summary: the community summary and the X thread, with copy buttons
  public/404.html              the page shown for an unknown address
  public/charts/*.svg          every chart on its own
  public/data/*.csv            the data behind every chart and table, plus figures.json
  public/downloads/            the report as PDF (Playwright print of build/print.html) and Word (python-docx)
  COMMUNITY-SUMMARY.md, METHOD.md
Every number in the text is read from data/figures.json or a CSV at build time; none is typed in by hand."""
import csv, html, json, re, shutil
from datetime import datetime, timezone
from pathlib import Path
import charts as C

ROOT = Path(__file__).resolve().parent.parent
PUB, DATA, BUILD = ROOT / "public", ROOT / "data", ROOT / "build"
SITE = "https://redbelly-onchain-holder.vercel.app"
PDF_NAME = "rbnt-holder-report-q3-2026.pdf"
DOCX_NAME = "rbnt-holder-report-q3-2026.docx"
TITLE = "RBNT holder report, Q3 2026"
SUB = "How RBNT holdings, staking and the publicly named wallets changed between 1 July and 30 September 2026, read from the Redbelly chain."
F = json.loads((DATA / "figures.json").read_text())
NAMED = json.loads((ROOT / "content/named_wallets.json").read_text())
TREASURY = json.loads((ROOT / "content/treasury_allocations.json").read_text())
RPC = "https://governors.mainnet.redbelly.network"
RS_API = "https://api.routescan.io/v2/network/mainnet/evm/151/etherscan/api"
EXPLORER = "https://redbelly.routescan.io"

def csv_rows(name):
    with open(DATA / name) as f:
        r = list(csv.reader(f))
    return r[0], r[1:]

def esc(s):
    return html.escape(str(s), quote=True)

# ---------- number formats ----------
def num(x, d=0):
    return f"{x:,.{d}f}"

def amt(x):
    """RBNT amounts in words for the text: 5.93 billion, 82.1 million, 15,724."""
    a = abs(x)
    if a >= 1e9:
        s = f"{x / 1e9:,.2f}".rstrip("0").rstrip(".") + " billion"
    elif a >= 1e6:
        s = f"{x / 1e6:,.1f}".removesuffix(".0") + " million"
    else:
        s = f"{x:,.0f}"
    return s

def pct(x, d=1):
    return f"{x:,.{d}f}%"

def when(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%-d %B %Y, %H:%M:%S UTC")

POOL_NL = next(a for a, p in F["pools"].items() if p["lock_days"] == 0)
POOL_LK = next(a for a, p in F["pools"].items() if p["lock_days"] == 365)
NL, LK = F["pools"][POOL_NL], F["pools"][POOL_LK]
W = F["where"]
by_name = {d["name"]: d for d in F["named"].values()}
ECO_U = by_name["Ecosystem (Unlocked)"]
START_AT, END_AT = when(F["start_block_time"]), when(F["end_block_time"])
FETCHED = datetime.strptime(F["fetched_utc"], "%Y-%m-%dT%H:%M:%SZ").strftime("%-d %B %Y")
CO = F["cohorts"]
_, _TR = csv_rows("07_reserved_wallet_transfers.csv")
def sent(wallet, to_prefix):
    """RBNT a reserved wallet sent to counterparties whose name starts with to_prefix, from 07_reserved_wallet_transfers.csv."""
    return sum(float(r[5]) for r in _TR if r[0] == wallet and r[1].startswith(to_prefix))
ECO_RELEASE = sent("Ecosystem (Locked)", "Ecosystem 2 (Unlocked)")
TO_POOLS = sent("Ecosystem (Unlocked)", "Reddex RBNT staking pool")
TO_WRBNT = sent("Ecosystem (Unlocked)", "Wrapped RBNT")
B = F["bands"]
up_bands = [k for k, v in B.items() if v["end"] > v["start"]]

# ---------- the report text ----------
# Inline marks: **bold**, [text](url). Block kinds: p, answer, plain, fig, table, ul, ol, dl.
FINDINGS = [
    f"**Staking grew.** RBNT staked in the two Reddex pools rose from {amt(F['staked_total_start'])} to {amt(F['staked_total_end'])}, "
    f"up {pct((F['staked_total_end'] / F['staked_total_start'] - 1) * 100)}. Most of the growth was in the no lock pool.",
    f"**Less RBNT was wrapped.** The Wrapped RBNT (WRBNT) supply fell from {amt(F['start_wrbnt_supply'])} to {amt(F['end_wrbnt_supply'])}, "
    f"and the RBNT backing it fell by exactly the same amount.",
    f"**Reserved wallets moved RBNT between themselves.** Ecosystem (Locked) released {amt(ECO_RELEASE)} to Ecosystem 2 (Unlocked), which sent "
    f"{amt(by_name['Investors']['in'])} to the Investors wallet. Governance (Locked) released {amt(by_name['Governance (Unlocked)']['in'])} "
    f"to Governance (Unlocked). Ecosystem (Unlocked) was the only reserved wallet that sent RBNT to addresses outside the reserved group.",
    f"**Holdings stayed concentrated.** The largest 100 community holders held {pct(F['top100_share_end'])} of community holdings at the end "
    f"of the quarter, against {pct(F['top100_share_start'])} at the start.",
    f"**The holder count edged up.** Addresses holding 1 RBNT or more (outside the named wallets) went from {num(F['holders_start_1plus'])} "
    f"to {num(F['holders_end_1plus'])}.",
]

SECTIONS = [
  {"id": "where", "title": "Where the RBNT is", "answer":
     f"At the end of the quarter, {pct(W['Redbelly reserved wallets']['end_pct'])} of all RBNT sat in Redbelly's reserved wallets, "
     f"{pct(W['Wrapped RBNT contract (backs WRBNT one to one)']['end_pct'])} backed Wrapped RBNT, {pct(W['Reddex pools: staked RBNT']['end_pct'])} "
     f"was staked in the Reddex pools and {pct(W['Other wallets']['end_pct'] + W['Other contracts']['end_pct'])} sat in all other wallets and contracts.",
   "blocks": [
     ("p", "RBNT is the coin of the Redbelly network. Every coin sits at an address, and anyone can read the balance of any address from "
           "the chain. This chart adds up every balance at the two dates and groups them by the kind of address that holds them."),
     ("fig", "where"),
     ("p", f"The balances read add up to {num(F['start_total_native'])} RBNT at the start and {num(F['end_total_native'])} at the end, and "
           f"the percentages in this report are shares of that total. Routescan quotes a total supply of 10,000,000,000 RBNT; the "
           f"{amt(1e10 - F['start_total_native'])} RBNT (about {pct((1e10 - F['start_total_native']) / 1e8, 2)}) not found is outside the "
           f"addresses read (see the method) or no longer in any balance, for example network fees burned since launch."),
     ("p", f"The **Wrapped RBNT contract** holds RBNT on behalf of people who hold WRBNT, a token version of RBNT used by apps. Each WRBNT "
           f"is backed by one RBNT in the contract, so the RBNT is counted once here, where it physically sits. In the rest of the report it "
           f"is counted with whoever holds the WRBNT."),
     ("p", f"The **Reddex pools** hold the RBNT people have staked plus the RBNT the pools use to pay rewards. The chart splits the two using "
           f"the pools' own record of how much is staked. **Other contracts** are addresses that run code, such as liquidity pools or "
           f"multi-signature wallets. **Other wallets** are ordinary addresses. Routescan publicly labels no exchange wallet on Redbelly, so "
           f"no exchange group appears; see section 6."),
     ("plain", "In plain words", f"Most RBNT has not moved into general circulation. Six in every ten coins are in wallets Redbelly has "
           f"publicly reserved for the team, investors, the ecosystem, governance, the reserve and research. Of the coins outside those "
           f"wallets, a growing part is staked."),
   ]},
  {"id": "holders", "title": "How many holders, and how big", "answer":
     f"{num(F['holders_end_1plus'])} addresses held 1 RBNT or more at the end of the quarter, up from {num(F['holders_start_1plus'])}. "
     f"Most hold small amounts: {num(B['1 to 100']['end'])} hold between 1 and 100 RBNT.",
   "blocks": [
     ("p", f"This section looks at every address that is not a named wallet, which we call **community holders**. For each one we add its "
           f"RBNT, its WRBNT and any RBNT it has staked in a Reddex pool, so a holder who stakes or wraps is not counted as having sold. "
           f"Holders are then sorted into size bands."),
     ("fig", "bands"),
     ("p", f"Between the two dates, {num(F['holders_new_1plus'])} addresses reached 1 RBNT or more and {num(F['holders_left_1plus'])} fell "
           f"below it. {num(F['holders_both_1plus'])} held 1 RBNT or more on both dates. The number of holders rose in "
           f"{len(up_bands)} of the {len(B)} bands."),
     ("p", f"One address is not always one person. A person can use many addresses, and one address, such as a contract, can hold RBNT "
           f"for many people. Counts of addresses are a guide to how widely RBNT is spread, not a count of people."),
   ]},
  {"id": "concentration", "title": "How concentrated holdings are", "answer":
     f"The largest 10 community holders held {pct(F['top10_share_end'])} of community holdings at the end of the quarter, "
     f"against {pct(F['top10_share_start'])} at the start. The largest 1,000 held {pct(F['top1000_share_end'])}.",
   "blocks": [
     ("p", "Concentration asks how much of the RBNT outside the named wallets sits with the biggest holders. The holders are ranked by "
           "size on each date, so the largest 10 at the end are not always the same addresses as the largest 10 at the start."),
     ("fig", "concentration"),
     ("p", f"A second measure, the Gini coefficient, sums up the whole spread in one number between 0 (everyone holds the same) and 1 "
           f"(one holder has everything). Among community holders with 1 RBNT or more it was {F['gini_start']:.4f} at the start and "
           f"{F['gini_end']:.4f} at the end. A value this close to 1 is common for a token that is a few years old with many small holders "
           f"and a few large ones."),
     ("p", f"{num(F['top100_entered'])} addresses were in the largest 100 at the end but not at the start."),
   ]},
  {"id": "largest", "title": "What the largest holders did", "answer":
     f"Among the 100 largest community holders at the start, {CO['ranks 11 to 100']['up'] + CO['largest 10']['up']} added more than 1% "
     f"over the quarter and {CO['ranks 11 to 100']['down'] + CO['largest 10']['down']} reduced by more than 1%.",
   "blocks": [
     ("p", "To see accumulation and selling without singling anyone out, the community holders are ranked by size at the start of the "
           "quarter and put into three groups. For every holder in a group we compare the end of the quarter with the start. A holder "
           "who staked or wrapped RBNT keeps the same total, because staked RBNT and WRBNT are counted with the holder."),
     ("fig", "cohorts"),
     ("table", "04_largest_holders.csv", "The three groups in numbers", None),
     ("p", f"Taken together, the largest 10 went from {amt(CO['largest 10']['start'])} to {amt(CO['largest 10']['end'])} RBNT, and ranks 11 "
           f"to 100 went from {amt(CO['ranks 11 to 100']['start'])} to {amt(CO['ranks 11 to 100']['end'])}. A fall in a group's total "
           f"means RBNT left those addresses; it does not show whether it was sold, moved to another address of the same owner, or put "
           f"into a contract. The chain records movements, not reasons."),
   ]},
  {"id": "staking", "title": "Staking in the Reddex pools", "answer":
     f"Staked RBNT rose by {amt(NL['stake_change'])} ({pct(NL['stake_change_pct'])}) in the no lock pool and by {amt(LK['stake_change'])} "
     f"({pct(LK['stake_change_pct'])}) in the 365 day pool.",
   "blocks": [
     ("p", "Staking means locking RBNT in a contract to earn rewards. Reddex runs two RBNT pools: one where RBNT can be taken out at any "
           "time, and one where each stake is locked for 365 days. Both pay rewards in RBNT."),
     ("fig", "staking"),
     ("p", f"A pool's balance is not the same as the amount staked. **Rewards are paid in RBNT from the pool's own balance, so a pool "
           f"balance may include reward funds as well as stakes.** The pools' own counter of staked RBNT (called totalStake) separates "
           f"the two, and the chart uses it. At the end of the quarter the no lock pool held {amt(NL['bal_end'])} RBNT, of which "
           f"{amt(NL['stake_end'])} was staked; the 365 day pool held {amt(LK['bal_end'])}, of which {amt(LK['stake_end'])} was staked."),
     ("fig", "staking_flows"),
     ("p", f"During the quarter, {num(NL['stake_accounts'])} addresses staked into the no lock pool and {num(NL['unstake_accounts'])} took "
           f"stakes out; for the 365 day pool the numbers were {num(LK['stake_accounts'])} and {num(LK['unstake_accounts'])}. The pools paid "
           f"out {amt(NL['claimed'])} RBNT (no lock) and {amt(LK['claimed'])} RBNT (365 day) in claimed rewards. "
           f"{num(F['stakers_unique_end'])} addresses had RBNT staked in at least one pool at the end of the quarter."),
     ("p", f"Staked RBNT was {pct(F['staked_share_of_community_start'])} of community holdings at the start and "
           f"{pct(F['staked_share_of_community_end'])} at the end."),
     ("p", f"The pools' verified source code names Ecosystem (Unlocked), one of Redbelly's reserved wallets, as their owner. That wallet "
           f"sent {amt(TO_POOLS)} RBNT to the pools as plain transfers during the quarter, not as stakes (it held no stake in either pool on "
           f"either date). Those transfers added to the funds the pools pay rewards from."),
     ("table", "pools_table", "Both pools in numbers", None),
   ]},
  {"id": "named", "title": "The publicly named wallets", "answer":
     f"Redbelly's reserved wallets held {amt(F['reserved_start'])} RBNT at the start and {amt(F['reserved_end'])} at the end. Most of "
     f"the movement was between reserved wallets; only Ecosystem (Unlocked) sent RBNT outside the group.",
   "blocks": [
     ("p", f"The DAO treasury page lists nine wallets Redbelly has reserved, with the amount each was allocated at launch. Those amounts "
           f"are allocations, not balances, so this section reads each wallet's balance from the chain on both dates and traces every "
           f"transfer in between."),
     ("fig", "reserved"),
     ("table", "reserved_table", "Reserved wallets: allocation, balances and transfers", None),
     ("p", f"The transfers fit together. Ecosystem (Locked) sent {amt(ECO_RELEASE)} RBNT to Ecosystem 2 (Unlocked), which then sent "
           f"{amt(by_name['Investors']['in'])} to the Investors wallet. Governance (Locked) sent {amt(by_name['Governance (Unlocked)']['in'])} "
           f"to Governance (Unlocked). None of these four transfers left the reserved group."),
     ("fig", "eco_unlocked"),
     ("p", f"Ecosystem (Unlocked) made {num(ECO_U['n_out'])} transfers out, {amt(ECO_U['out'])} RBNT in total, and paid "
           f"{num(ECO_U['fees'], 0)} RBNT in network fees. Of this, {amt(TO_WRBNT)} went into the Wrapped RBNT contract (wrapping it into WRBNT), "
           f"{amt(TO_POOLS)} went to the Reddex pools as reward funds, and the rest went to unlabelled wallets and contracts, which this report "
           f"counts only as a group."),
     ("h3", "Exchanges"),
     ("p", f"The brief asks for flows in and out of labelled exchange wallets. On {FETCHED}, Routescan's public address list for Redbelly "
           f"mainnet carried a name for {num(len(F['labelled_on_routescan']))} address, the Wrapped RBNT contract, and labelled no exchange "
           f"wallet. With no public label to go by, this edition reports no exchange flows. Naming an unlabelled address as an exchange would "
           f"be a guess about who controls it, which this report does not make. The method explains how the next edition picks up labels "
           f"as soon as Routescan publishes them."),
     ("h3", "Every named wallet adds up"),
     ("p", "For each named wallet, the balance at the start plus everything received, minus everything sent and the fees paid, gives the "
           "balance at the end exactly. The gap is zero for all twelve named addresses (see the reconciliation column in "
           "06_named_wallets.csv)."),
   ]},
]

METHOD = [
  ("p", f"The report compares two moments: the end of 30 June 2026 and the end of 30 September 2026. Each is the last block before "
        f"midnight UTC: block {num(F['start_block'])} ({START_AT}) and block {num(F['end_block'])} ({END_AT}). Every balance, every pool "
        f"figure and every WRBNT balance is read from the chain at exactly these two blocks."),
  ("ol", [
     f"**Find every address.** Take every address that sent or received a transaction or an internal transfer since the start block "
     f"(read block by block from the RPC, plus Routescan's internal transfers), the named wallets, and Routescan's address list in "
     f"balance order. Routescan reports about {num(F['listing_approx_total'])} addresses; {num(F['listing_count'])} were read, down to "
     f"addresses it lists with {F['listing_read_to_rbnt']} RBNT, before its free rate limit stopped further pages on {FETCHED}. Addresses "
     f"further down the list show {F['listing_read_to_rbnt']} RBNT or less, so they can only affect the two smallest size bands, and any of "
     f"them that moved RBNT during the quarter was read anyway.",
     f"**Read balances from the chain.** Call eth_getBalance for every address at both blocks on the Redbelly RPC "
     f"({num(F['read_from_chain'])} addresses). The explorer list is only used to find addresses, never for balances: of the "
     f"{num(F['listing_check']['unmoved_addresses_compared'])} listed addresses that did not move during the quarter, the list showed the "
     f"chain balance exactly for {num(F['listing_check']['exact'])}, rounded for {num(F['listing_check']['rounded_in_listing'])}, and a "
     f"different balance for {num(F['listing_check']['different'])}, most of them a balance the chain shows as zero.",
     "**Read WRBNT.** Call balanceOf and totalSupply on the WRBNT contract at both blocks for every address that has ever held WRBNT "
     "(Routescan's holder list plus every Transfer event since the start block). Check that the WRBNT supply equals the RBNT held by the "
     "contract and the sum of all WRBNT balances.",
     "**Read the pools.** Call totalStake and lockPeriod on each pool at both blocks, and userInfo for every address that has ever "
     "staked (every stake() call to the pool). Check that the stakers' amounts add up to totalStake. Read the Stake, Unstake and "
     "ClaimLiquidXReward events in the quarter.",
     "**Build positions.** For each address add native RBNT, WRBNT and staked RBNT. Leave out the WRBNT contract and the staked part of "
     "each pool, so no RBNT is counted twice.",
     "**Group.** Named wallets are reported by name. Every other address is a community holder and appears only in counts and totals of "
     "groups (size bands and rank groups). No group of fewer than 5 holders is reported.",
     "**Trace named wallets.** List every transaction and internal transfer of each named wallet in the quarter from Routescan's API, "
     "leave out failed calls and delegate calls, and check that the start balance plus inflows minus outflows and fees equals the end "
     "balance.",
  ]),
  ("plain", "Pool balances include reward funds", "Rewards in both Reddex pools are paid in RBNT from the pool's own balance. A pool's "
        "RBNT balance therefore may include reward funds as well as stakes. This report measures staking with the pools' totalStake figure "
        "and the stakers' own amounts, and shows the rest of the balance separately as reward funds."),
  ("plain", "WRBNT is counted once", "Each WRBNT is backed by one RBNT held by the WRBNT contract. Where RBNT physically sits (section 1) "
        "counts the contract's RBNT. Everywhere else the contract is left out and the RBNT is counted with whoever holds the WRBNT."),
  ("p", f"**Checks that ran on this data.** The WRBNT supply equalled the RBNT in the WRBNT contract and the sum of WRBNT balances on both "
        f"dates, to the last unit. Each pool's stakers added up to its totalStake on both dates, and the quarter's Stake minus Unstake events "
        f"equalled the change in totalStake. Every named wallet reconciled to zero. The scripts stop with an error if any of these fail."),
  ("p", "**What the chain does not show.** Who controls an address, why RBNT moved, and whether a transfer was a sale. The report describes "
        "movements only. It makes no forecast and gives no advice."),
]

GLOSSARY = [
  ("Address", "A public account on the chain, written as 0x followed by 40 characters. It can belong to a person, a company or a program."),
  ("Wallet", "An address controlled by a private key, usually belonging to a person or an organisation."),
  ("Contract", "An address that runs code, such as a staking pool, a token or a multi-signature wallet."),
  ("Block", "A batch of transactions. Each block has a number and a time, so a block number fixes a moment."),
  ("Staking", "Locking RBNT in a contract to earn rewards."),
  ("WRBNT", "Wrapped RBNT, a token backed one to one by RBNT held in the WRBNT contract."),
  ("Reserved wallets", "The nine wallets the DAO treasury page lists for team, investors, reserve, ecosystem, governance and USYD/CSIRO."),
  ("Community holders", "Every address in this report that is not a named wallet."),
  ("RPC", "The public interface to a Redbelly node, used here to read balances at a given block."),
  ("Explorer", "A website that shows chain data, here Routescan."),
]

SOURCES = [
  ("Redbelly mainnet RPC (chain ID 151)", RPC, "Native balances, WRBNT balances and supply, pool totalStake, lockPeriod and userInfo, block times, "
   "every block's transactions, and contract code, all at the two quarter blocks or for the blocks in between.", f"Read {FETCHED}"),
  ("Routescan explorer API, Etherscan compatible", RS_API, "Transactions and internal transfers of the named wallets and the pools in the "
   "quarter; internal transfers of every block since the start block; verified source code of the pools.", f"Read {FETCHED}"),
  ("Routescan address list", "https://api.routescan.io/v2/network/mainnet/evm/151/addresses", "Every address with a balance, used only to "
   "find addresses, and the public names Routescan gives addresses.", f"Read {F['listing_fetched_utc'][:10]}"),
  ("Routescan WRBNT holder list", "https://api.routescan.io/v2/network/mainnet/evm/151/erc20/0x6ed1f491e2d31536d6561f6bdb2adc8f092a6076/holders",
   "Addresses that hold WRBNT, used only to find addresses.", f"Read {FETCHED}"),
  ("Redbelly DAO treasury page", "https://redbellydao.network/treasury/", "Names, addresses and launch allocations of the nine reserved wallets "
   "(read from the table in the page's script; its address and SHA-256 are in evidence/manifest.json).", f"Read {FETCHED}"),
  ("Reddex staking", "https://www.reddex.io/stake", "The two RBNT pools. Their verified source code is published on Routescan; SHA-256 in evidence/manifest.json.", f"Read {FETCHED}"),
]

THREAD = [
  f"RBNT holder report, Q3 2026 (1 July to 30 September), read straight from the Redbelly chain. Trends only, no wallet owners named "
  f"beyond Redbelly's public reserved wallets. Not financial advice. {SITE}",
  f"1. Staking grew. RBNT staked in the two Reddex pools went from {amt(F['staked_total_start'])} to {amt(F['staked_total_end'])} "
  f"(no lock pool +{amt(NL['stake_change'])}, 365 day pool +{amt(LK['stake_change'])}).",
  f"2. Less RBNT was wrapped. WRBNT supply fell from {amt(F['start_wrbnt_supply'])} to {amt(F['end_wrbnt_supply'])}. The RBNT backing it "
  f"fell by the same amount, so WRBNT stayed fully backed.",
  f"3. Reserved wallets: {amt(ECO_RELEASE)} moved from Ecosystem (Locked) to Ecosystem 2 (Unlocked), then {amt(by_name['Investors']['in'])} to "
  f"Investors. Governance (Locked) released {amt(by_name['Governance (Unlocked)']['in'])} to Governance (Unlocked). All inside the reserved group.",
  f"4. Holders: {num(F['holders_end_1plus'])} addresses held 1+ RBNT at quarter end, up from {num(F['holders_start_1plus'])}. The largest "
  f"100 community holders held {pct(F['top100_share_end'])} of community holdings, from {pct(F['top100_share_start'])}.",
  f"5. Exchanges: Routescan labels no exchange wallet on Redbelly yet, so the report shows no exchange flows rather than guess. Every "
  f"number, the data and the method are public so anyone can check or repeat it: {SITE}",
]

SUMMARY_PARAS = [
  f"The first quarterly RBNT holder report covers 1 July to 30 September 2026. Every number is read from the Redbelly chain at the last "
  f"block before midnight UTC on 30 June and on 30 September. It describes trends in groups and names only wallets that are already public. "
  f"It is not financial advice and makes no price forecast.",
  f"Staking grew over the quarter. RBNT staked in the two Reddex pools rose from {amt(F['staked_total_start'])} to "
  f"{amt(F['staked_total_end'])}. At the same time the supply of Wrapped RBNT fell from {amt(F['start_wrbnt_supply'])} to "
  f"{amt(F['end_wrbnt_supply'])}, with the RBNT backing it falling by the same amount.",
  f"Most RBNT still sits in Redbelly's reserved wallets: {pct(W['Redbelly reserved wallets']['end_pct'])} at the end of the quarter. "
  f"The largest movements were between those wallets: {amt(ECO_RELEASE)} from Ecosystem (Locked) to Ecosystem 2 (Unlocked), "
  f"{amt(by_name['Investors']['in'])} from there to the Investors wallet, and {amt(by_name['Governance (Unlocked)']['in'])} from "
  f"Governance (Locked) to Governance (Unlocked). Ecosystem (Unlocked) was the only reserved wallet that sent RBNT outside the group, "
  f"including {amt(TO_POOLS)} to the staking pools for rewards.",
  f"Outside the named wallets, {num(F['holders_end_1plus'])} addresses held 1 RBNT or more at the end of the quarter, up from "
  f"{num(F['holders_start_1plus'])}, and the largest 100 held {pct(F['top100_share_end'])} of community holdings. Routescan labels no "
  f"exchange wallet on Redbelly yet, so the report shows no exchange flows rather than guess. The full report, the data and the method "
  f"are at {SITE}.",
]

# ---------- inline marks ----------
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
def rich(t):
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return LINK.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', t)

def plain(t):
    return LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", t.replace("**", ""))

# ---------- charts ----------
def chart_specs():
    order = ["Redbelly reserved wallets", "Wrapped RBNT contract (backs WRBNT one to one)", "Other wallets", "Reddex pools: staked RBNT",
             "Other contracts", "Reddex pools: reward funds"]
    short = {"Wrapped RBNT contract (backs WRBNT one to one)": "Wrapped RBNT contract", "Reddex pools: staked RBNT": "Reddex pools, staked",
             "Reddex pools: reward funds": "Reddex pools, reward funds"}
    s = {}
    s["where"] = ("Where the RBNT sits, by kind of address", "01_where_the_rbnt_sits.csv",
                  C.paired_bars([(short.get(k, k), W[k]["start"], W[k]["end"]) for k in order],
                                "Where the RBNT sits", "RBNT held by each kind of address at the start and end of the quarter.", C.big))
    bands = list(B)
    s["bands"] = ("Community holders by size of holding, number of addresses", "02_holders_by_size.csv",
                  C.paired_bars([(k + " RBNT" if k != "under 1" else "under 1 RBNT", B[k]["start"], B[k]["end"]) for k in bands],
                                "Community holders by size", "Number of addresses in each holding size band at the start and end of the quarter.",
                                lambda v: num(v), label_w=210))
    s["concentration"] = ("Share of community holdings held by the largest holders", "03_concentration.csv",
                          C.dumbbell([(f"Largest {n:,}", F[f"top{n}_share_start"], F[f"top{n}_share_end"]) for n in (10, 100, 1000)],
                                     "Concentration", "Share of community holdings held by the largest 10, 100 and 1,000 holders.",
                                     lambda v: f"{v:.1f}%", vmax=100))
    parts = [("Added more than 1%", "s4"), ("Within 1%", "s3"), ("Reduced more than 1%", "s2"), ("Below 1 RBNT at end", "s1")]
    s["cohorts"] = ("What the largest holders did over the quarter, number of addresses", "04_largest_holders.csv",
                    C.stacked_100([(k, [v["up"], v["flat"], v["down"], v["gone"]]) for k, v in CO.items()], parts,
                                  "What the largest holders did", "For the holders ranked largest at the start, how many added, held, reduced or left."))
    s["staking"] = ("RBNT staked in each Reddex pool", "05_staking_pools.csv",
                    C.paired_bars([("No lock pool", NL["stake_start"], NL["stake_end"]), ("365 day pool", LK["stake_start"], LK["stake_end"])],
                                  "RBNT staked", "Staked RBNT (totalStake) in each pool at the start and end of the quarter.", C.big, label_w=150))
    s["staking_flows"] = ("RBNT staked and unstaked during the quarter", "05_staking_pools.csv",
                          C.flow_bars([("No lock pool", NL["staked"], NL["unstaked"]), ("365 day pool", LK["staked"], LK["unstaked"])],
                                      "Stake and unstake", "RBNT put into and taken out of each pool during the quarter.", C.big, label_w=150,
                                      left="Unstaked", right="Staked"))
    res = [w for w in NAMED if w["group"] == "reserved"]
    s["reserved"] = ("Native RBNT in each reserved wallet", "06_named_wallets.csv",
                     C.paired_bars([(w["name"], F["named"][w["address"].lower()]["start"], F["named"][w["address"].lower()]["end"]) for w in res],
                                   "Reserved wallets", "RBNT in each of Redbelly's nine reserved wallets at the start and end of the quarter.", C.big, label_w=190))
    hdr, rows = csv_rows("07_reserved_wallet_transfers.csv")
    eco = [r for r in rows if r[0] == "Ecosystem (Unlocked)"]
    s["eco_unlocked"] = ("Where Ecosystem (Unlocked) sent RBNT", "07_reserved_wallet_transfers.csv",
                         C.flow_bars([(r[1].replace("Reddex RBNT staking pool, ", "Reddex pool, ").replace("Wrapped RBNT (WRBNT) contract", "Wrapped RBNT contract")
                                       .replace("unlabelled", "Unlabelled"), 0, float(r[5])) for r in eco],
                                     "Ecosystem (Unlocked) transfers out", "RBNT sent by Ecosystem (Unlocked) during the quarter, by recipient.",
                                     C.big, label_w=210, left="Sent", right=None))
    return s

# ---------- tables ----------
def table_data(name, cols):
    if name == "reserved_table":
        head = ["Wallet", "Allocated at launch", "Start", "End", "Change", "Transfers in", "Transfers out"]
        rows = []
        for w in NAMED:
            if w["group"] != "reserved":
                continue
            d = F["named"][w["address"].lower()]
            rows.append([w["name"], TREASURY.get(w["address"].lower(), "none listed"), num(d["start"]), num(d["end"]),
                         ("+" if d["end"] - d["start"] > 0 else "") + num(d["end"] - d["start"]), num(d["n_in"]), num(d["n_out"])])
        return head, rows
    if name == "pools_table":
        lines = [("Lock", lambda p: "none" if p["lock_days"] == 0 else f"{p['lock_days']} days"),
                 ("RBNT balance, start", lambda p: num(p["bal_start"])), ("RBNT balance, end", lambda p: num(p["bal_end"])),
                 ("Staked (totalStake), start", lambda p: num(p["stake_start"])), ("Staked (totalStake), end", lambda p: num(p["stake_end"])),
                 ("Change in staked", lambda p: f"+{num(p['stake_change'])} ({pct(p['stake_change_pct'])})"),
                 ("Balance minus staked (reward funds), start", lambda p: num(p["rest_start"])),
                 ("Balance minus staked (reward funds), end", lambda p: num(p["rest_end"])),
                 ("Stakers, start", lambda p: num(p["stakers_start"])), ("Stakers, end", lambda p: num(p["stakers_end"])),
                 ("RBNT staked in the quarter", lambda p: f"{num(p['staked'])} ({num(p['stake_tx'])} stakes, {num(p['stake_accounts'])} addresses)"),
                 ("RBNT unstaked in the quarter", lambda p: f"{num(p['unstaked'])} ({num(p['unstake_tx'])} unstakes, {num(p['unstake_accounts'])} addresses)"),
                 ("Rewards claimed in the quarter", lambda p: f"{num(p['claimed'])} ({num(p['claim_tx'])} claims, {num(p['claim_accounts'])} addresses)")]
        return ["", "No lock pool", "365 day pool"], [[k, f(NL), f(LK)] for k, f in lines]
    head, rows = csv_rows(name)
    if cols:
        head = [head[i] for i in cols]; rows = [[r[i] for i in cols] for r in rows]
    def fmt(x):
        try:
            v = float(x)
        except ValueError:
            return x
        return num(v, 2) if abs(v) < 10 and v != int(v) else num(v)
    return head, [[fmt(c) for c in r] for r in rows]

def table_html(head, rows):
    def is_num(c):
        return bool(re.fullmatch(r"[+-]?[\d,]+(\.\d+)?%?", c))
    th = "".join(f'<th class="{"r" if i else ""}">{esc(h)}</th>' for i, h in enumerate(head))
    tr = "".join("<tr>" + "".join(f'<td class="{"r" if i and is_num(c) else ""}">{esc(c)}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'

# ---------- web page ----------
FIGNO = {}
def number_figures():
    n = 0
    for s in SECTIONS:
        for b in s["blocks"]:
            if b[0] == "fig":
                n += 1; FIGNO[b[1]] = n

def figure_html(key, specs, mode):
    title, csvname, svg = specs[key]
    n = FIGNO[key]
    head, rows = csv_rows(csvname)
    src = (f'Source: Redbelly mainnet, read at blocks {num(F["start_block"])} and {num(F["end_block"])}. '
           f'Data: <a href="data/{csvname}">{csvname}</a>')
    tbl = "" if mode == "print" else (f'<details class="tbl"><summary>Show the data as a table</summary><div class="tw">'
                                      f'{table_html(*table_data(csvname, None))}</div></details>')
    return (f'<figure class="rise" id="fig-{key}"><div class="fh"><div class="fn">FIGURE {n}</div><h4>{esc(title)}</h4></div>'
            f'<div class="chart">{svg}</div><figcaption>{src}</figcaption>{tbl}</figure>')

def blocks_html(blocks, specs, mode):
    out = []
    for b in blocks:
        k = b[0]
        if k == "p":
            out.append(f'<p class="rise">{rich(b[1])}</p>')
        elif k == "h3":
            out.append(f'<h3 class="rise">{esc(b[1])}</h3>')
        elif k == "plain":
            out.append(f'<div class="plain rise"><b>{esc(b[1])}</b><p>{rich(b[2])}</p></div>')
        elif k == "fig":
            out.append(figure_html(b[1], specs, mode))
        elif k == "table":
            out.append(f'<div class="solo rise"><div class="fh" style="padding:14px 18px 0"><h4 style="margin:0;font-size:15px">{esc(b[2])}</h4></div>'
                       f'<div class="tw">{table_html(*table_data(b[1], b[3]))}</div></div>')
        elif k in ("ul", "ol"):
            cls = ' class="steps"' if k == "ol" else ""
            out.append(f'<{k}{cls}>' + "".join(f'<li class="rise">{rich(x)}</li>' for x in b[1]) + f'</{k}>')
    return "".join(out)

def head_html(title, desc, path):
    return (f'<!doctype html><html lang="en-AU"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">'
            f'<link rel="canonical" href="{SITE}{path}"><meta property="og:title" content="{esc(title)}">'
            f'<meta property="og:description" content="{esc(desc)}"><meta property="og:image" content="{SITE}/brand/og.png">'
            f'<meta property="og:type" content="article"><meta name="twitter:card" content="summary_large_image">'
            f'<meta name="theme-color" content="#0c1317"><link rel="icon" href="/brand/icon-32.png" sizes="32x32">'
            f'<link rel="apple-touch-icon" href="/brand/icon-180.png"><link rel="stylesheet" href="/report.css">'
            f'<script>document.documentElement.classList.add("js")</script></head>')

def bar_html(current):
    def a(href, label, key, cls=""):
        cur = ' aria-current="page"' if key == current else ""
        return f'<a href="{href}"{cur}{cls}>{label}</a>'
    return (f'<a class="skip" href="#main">Skip to the report</a><header class="bar"><div class="bar-in">'
            f'<a href="/" aria-label="Report home"><img src="/brand/dao-logo-on-dark.png" alt="Redbelly DAO" width="42" height="30"></a>'
            f'<div class="ttl">RBNT holder report <span>Q3 2026</span></div><nav aria-label="Pages">'
            + a("/", "Report", "home") + a("/summary", "Summary", "summary") + a("/#method", "Method", "method", ' class="wide"')
            + a(f"/downloads/{PDF_NAME}", "PDF", "pdf", ' class="dl"') + a(f"/downloads/{DOCX_NAME}", "Word", "docx", ' class="dl"')
            + '</nav></div><div class="progress" aria-hidden="true"></div></header>')

def foot_html():
    return (f'<footer class="foot"><div class="in"><span>Redbelly DAO community research. On-chain data read {FETCHED}. '
            f'Not financial advice.</span><span><a href="/data/figures.json">figures.json</a> · <a href="/#sources">Sources</a> · '
            f'<a href="/#data">Data</a></span></div></footer>')

def tiles():
    t = [
        (f"{amt(F['staked_total_end']).split()[0]}<small>{amt(F['staked_total_end']).split()[1]}</small>", "RBNT staked in the Reddex pools at quarter end",
         f"from {amt(F['staked_total_start'])}"),
        (f"{num(F['holders_end_1plus'])}", "addresses holding 1 RBNT or more, outside the named wallets", f"from {num(F['holders_start_1plus'])}"),
        (f"{F['top100_share_end']:.1f}<small>%</small>", "of community holdings held by the largest 100 holders", f"from {pct(F['top100_share_start'])}"),
        (f"{amt(F['reserved_end']).split()[0]}<small>{amt(F['reserved_end']).split()[1]}</small>", "RBNT in Redbelly's nine reserved wallets",
         f"from {amt(F['reserved_start'])}"),
    ]
    return '<div class="tiles">' + "".join(f'<div class="tile"><div class="n">{n}</div><div class="l">{esc(l)}</div><div class="s">{esc(s)}</div></div>' for n, l, s in t) + "</div>"

def toc_items():
    return [(s["id"], f"{i}. {s['title']}") for i, s in enumerate(SECTIONS, 1)] + [("method", f"{len(SECTIONS) + 1}. Method"),
            ("sources", f"{len(SECTIONS) + 2}. Sources"), ("data", f"{len(SECTIONS) + 3}. The data"), ("terms", "Words used")]

def body_sections(specs, mode):
    out = []
    out.append(f'<section id="glance" aria-labelledby="h-glance"><div class="num">AT A GLANCE</div><h2 id="h-glance">The quarter in five points</h2>'
               f'<ul class="steps">' + "".join(f'<li class="rise">{rich(x)}</li>' for x in FINDINGS) + '</ul>'
               f'<div class="plain rise"><b>Read this first</b><p>This report describes what the public Redbelly chain shows. It names only '
               f'wallets that are already public: Redbelly\'s reserved wallets from the DAO treasury page, the Wrapped RBNT contract and the two '
               f'Reddex staking pools. Every other address is counted only inside a group. It is not financial advice and it makes no forecast '
               f'of price.</p></div></section>')
    for i, s in enumerate(SECTIONS, 1):
        out.append(f'<section id="{s["id"]}" aria-labelledby="h-{s["id"]}"><div class="num">SECTION {i}</div><h2 id="h-{s["id"]}">{esc(s["title"])}</h2>'
                   f'<p class="answer rise">{rich(s["answer"])}</p>{blocks_html(s["blocks"], specs, mode)}</section>')
    n = len(SECTIONS)
    out.append(f'<section id="method" aria-labelledby="h-method"><div class="num">SECTION {n + 1}</div><h2 id="h-method">Method: how to repeat this report</h2>'
               f'<p class="answer rise">Anyone can produce the next edition by changing two dates and running two scripts. Every step reads public data.</p>'
               f'{blocks_html(METHOD, specs, mode)}<p class="rise">To repeat it: set the quarter in <code>scripts/fetch.py</code>, run '
               f'<code>python3 scripts/fetch.py</code>, then <code>python3 scripts/analyse.py</code>, <code>python3 scripts/build.py</code> and '
               f'<code>python3 scripts/check.py</code>. METHOD.md in the repository gives every call in detail.</p></section>')
    src_rows = "".join(f'<tr><td><strong>{esc(t)}</strong><br><a href="{esc(u)}">{esc(u)}</a></td><td>{esc(w)}</td><td class="r">{esc(d)}</td></tr>'
                       for t, u, w, d in SOURCES)
    out.append(f'<section id="sources" aria-labelledby="h-sources"><div class="num">SECTION {n + 2}</div><h2 id="h-sources">Sources and dates</h2>'
               f'<p class="rise">Every figure in this report is a balance or event on the Redbelly chain at block {num(F["start_block"])} '
               f'({START_AT}) or block {num(F["end_block"])} ({END_AT}), or an event between them. The data was read on {FETCHED}.</p>'
               f'<div class="solo rise"><div class="tw"><table class="src"><thead><tr><th>Source</th><th>What was read</th><th class="r">When</th></tr></thead>'
               f'<tbody>{src_rows}</tbody></table></div></div></section>')
    files = [("01_where_the_rbnt_sits.csv", "Section 1, figure 1"), ("02_holders_by_size.csv", "Section 2, figure 2"),
             ("03_concentration.csv", "Section 3, figure 3"), ("04_largest_holders.csv", "Section 4, figure 4"),
             ("05_staking_pools.csv", "Section 5, figures 5 and 6"), ("06_named_wallets.csv", "Section 6, figure 7, reconciliation"),
             ("07_reserved_wallet_transfers.csv", "Section 6, figure 8"), ("figures.json", "Every number quoted in the text, and the checks")]
    out.append(f'<section id="data" aria-labelledby="h-data"><div class="num">SECTION {n + 3}</div><h2 id="h-data">The data</h2>'
               f'<p class="rise">The data behind every chart and table. Each file names named wallets only; other addresses appear only as counts '
               f'and totals.</p><div class="solo rise"><div class="tw"><table><thead><tr><th>File</th><th>Used in</th></tr></thead><tbody>'
               + "".join(f'<tr><td><a href="data/{f}"><code>{f}</code></a></td><td>{u}</td></tr>' for f, u in files) + '</tbody></table></div></div></section>')
    out.append('<section id="terms" aria-labelledby="h-terms"><div class="num">WORDS USED</div><h2 id="h-terms">Words used in this report</h2><dl class="gl">'
               + "".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in GLOSSARY) + "</dl></section>")
    return "".join(out)

def band_html():
    return (f'<div class="band"><div class="band-in"><div class="kicker"><span class="dot">QUARTERLY ON-CHAIN REPORT</span><span>Edition 1</span>'
            f'<span>1 July to 30 September 2026</span></div><h1>{esc(TITLE)}</h1><p class="lede">{esc(SUB)} Trends in groups, never individual '
            f'holders. Not financial advice.</p>{tiles()}<div class="fine">Blocks {num(F["start_block"])} and {num(F["end_block"])} on Redbelly '
            f'mainnet (chain ID 151). Data read {FETCHED}.</div></div></div>')

JS = """(function(){var bar=document.querySelector('.progress'),links=[].slice.call(document.querySelectorAll('.toc a')),
secs=links.map(function(a){return document.getElementById(a.getAttribute('href').slice(1))});
function onScroll(){var h=document.documentElement,max=h.scrollHeight-h.clientHeight;if(bar)bar.style.width=(max>0?h.scrollTop/max*100:0)+'%';
var cur=0;secs.forEach(function(s,i){if(s&&s.getBoundingClientRect().top<120)cur=i});links.forEach(function(a,i){a.classList.toggle('on',i===cur)})}
addEventListener('scroll',onScroll,{passive:true});onScroll();
var els=document.querySelectorAll('.rise');if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){
if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{rootMargin:'0px 0px -6% 0px'});els.forEach(function(e){io.observe(e)})}
else{els.forEach(function(e){e.classList.add('in')})}
document.querySelectorAll('button[data-copy]').forEach(function(b){b.addEventListener('click',function(){var t=document.getElementById(b.dataset.copy).innerText;
navigator.clipboard.writeText(t).then(function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1500)})})})})();"""

def home_page(specs):
    toc = "".join(f'<li><a href="#{i}">{esc(t)}</a></li>' for i, t in toc_items())
    return (head_html(TITLE, SUB, "/") + "<body>" + bar_html("home") + band_html()
            + f'<div class="wrap"><nav class="toc" aria-label="Contents"><b>Contents</b><ol>{toc}</ol></nav><main id="main">'
            + body_sections(specs, "web") + f'</main></div>{foot_html()}<script>{JS}</script></body></html>')

def summary_page():
    paras = "".join(f"<p>{esc(p)}</p>" for p in SUMMARY_PARAS)
    posts = "".join(f'<div class="post"><p id="post{i}">{esc(p)}</p><div class="meta"><span>{i}/{len(THREAD)} · {len(p)} characters</span>'
                    f'<button type="button" data-copy="post{i}">Copy</button></div></div>' for i, p in enumerate(THREAD, 1))
    return (head_html("Community summary, RBNT holder report Q3 2026", "A short summary of the Q3 2026 RBNT holder report and an X thread.", "/summary")
            + "<body>" + bar_html("summary") + f'<div class="band"><div class="band-in"><div class="kicker"><span class="dot">COMMUNITY SUMMARY</span>'
            f'<span>Q3 2026</span></div><h1>The quarter in a few paragraphs</h1><p class="lede">Ready to share. Every number comes from the '
            f'<a href="/">full report</a>. Not financial advice.</p></div></div><div class="wrap" style="display:block"><main id="main" style="max-width:760px">'
            f'<section><div class="num">PARAGRAPHS</div><h2>Summary</h2><div id="paras">{paras}</div>'
            f'<p><button type="button" class="copyall" data-copy="paras" style="font:500 13px var(--sans);border:1px solid var(--line-2);background:var(--card);color:var(--ink);border-radius:4px;padding:8px 12px;cursor:pointer">Copy</button></p></section>'
            f'<section><div class="num">X THREAD</div><h2>As an X thread</h2>{posts}</section></main></div>{foot_html()}<script>{JS}</script></body></html>')

def not_found_page():
    return (head_html("Page not found", "This address does not exist.", "/404") + "<body>" + bar_html("") +
            '<div class="band"><div class="band-in"><div class="kicker"><span class="dot">404</span></div><h1>This page does not exist</h1>'
            '<p class="lede"><a href="/">Go to the report</a></p></div></div></body></html>')

def print_page(specs):
    css = (ROOT / "scripts/report.css").read_text().replace("url(fonts/", f"url({(PUB / 'fonts').as_uri()}/")
    pcss = (ROOT / "scripts/print.css").read_text()
    body = body_sections(specs, "print")
    body = body.replace('href="data/', f'href="{SITE}/data/')
    return (f'<!doctype html><html lang="en-AU" data-theme="light"><head><meta charset="utf-8"><title>{esc(TITLE)}</title>'
            f'<style>{css}{pcss}</style></head><body class="print">{band_html()}<main>{body}</main></body></html>')

# ---------- Word ----------
def docx_link(par, url, text=None):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    rid = par.part.relate_to(url, RT.HYPERLINK, is_external=True)
    h = OxmlElement("w:hyperlink"); h.set(qn("r:id"), rid)
    r = OxmlElement("w:r"); pr = OxmlElement("w:rPr")
    c = OxmlElement("w:color"); c.set(qn("w:val"), "B3272A"); pr.append(c)
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single"); pr.append(u)
    r.append(pr); t = OxmlElement("w:t"); t.text = text or url; t.set(qn("xml:space"), "preserve"); r.append(t)
    h.append(r); par._p.append(h)

def docx_rich(par, text):
    for part in re.split(r"(\*\*.+?\*\*)", text):
        if part.startswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part:
            par.add_run(plain(part))

def clean_app_props(path):
    import zipfile, tempfile
    tmp = Path(tempfile.mkstemp(suffix=".docx")[1])
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/thumbnail.jpeg":
                continue
            if item.filename in ("_rels/.rels", "[Content_Types].xml"):
                data = re.sub(rb'<(Relationship|Override)[^>]*thumbnail[^>]*/>', b"", data)
            if item.filename == "docProps/app.xml":
                data = re.sub(rb"<Application>.*?</Application>", b"<Application></Application>", data)
                data = re.sub(rb"<AppVersion>.*?</AppVersion>", b"", data)
                data = re.sub(rb"<Company>.*?</Company>", b"<Company></Company>", data)
            zout.writestr(item, data)
    shutil.move(str(tmp), path)

def build_docx(path, specs, pngs):
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    d = Document()
    st = d.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
    for sec in d.sections:
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.2)
    for name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        d.styles[name].font.color.rgb = RGBColor(0x0F, 0x1A, 0x22)
    def table(head, rows):
        t = d.add_table(rows=1, cols=len(head)); t.style = "Light Grid Accent 2"
        for i, x in enumerate(head):
            t.rows[0].cells[i].text = x
        for r in rows:
            c = t.add_row().cells
            for i, x in enumerate(r):
                c[i].text = x
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8.5)
    def blocks(bs):
        for b in bs:
            k = b[0]
            if k == "p":
                docx_rich(d.add_paragraph(), b[1])
            elif k == "h3":
                d.add_heading(b[1], 3)
            elif k == "plain":
                p = d.add_paragraph(); r = p.add_run(b[1] + ". "); r.bold = True; docx_rich(p, b[2])
            elif k == "fig":
                title, csvname, _ = specs[b[1]]
                p = d.add_paragraph(); r = p.add_run(f"Figure {FIGNO[b[1]]}. {title}"); r.bold = True; p.paragraph_format.keep_with_next = True
                d.add_picture(str(pngs[b[1]]), width=Cm(16.4))
                c = d.add_paragraph(f"Source: Redbelly mainnet, read at blocks {num(F['start_block'])} and {num(F['end_block'])}. Data: {csvname}")
                c.runs[0].font.size = Pt(8.5); c.runs[0].font.color.rgb = RGBColor(0x4B, 0x5A, 0x64)
            elif k == "table":
                d.add_paragraph().add_run(b[2]).bold = True
                table(*table_data(b[1], b[3]))
            elif k in ("ul", "ol"):
                for i, x in enumerate(b[1], 1):
                    docx_rich(d.add_paragraph(style="List Number" if k == "ol" else "List Bullet"), x)
    d.add_heading(TITLE, 0)
    d.add_paragraph(SUB).runs[0].italic = True
    d.add_paragraph(f"Quarterly on-chain report, edition 1. Blocks {num(F['start_block'])} ({START_AT}) and {num(F['end_block'])} ({END_AT}) "
                    f"on Redbelly mainnet. Data read {FETCHED}.")
    p = d.add_paragraph("Web version, with the data: "); docx_link(p, SITE)
    d.add_heading("Read this first", 1)
    d.add_paragraph("This report describes what the public Redbelly chain shows. It names only wallets that are already public: Redbelly's "
                    "reserved wallets from the DAO treasury page, the Wrapped RBNT contract and the two Reddex staking pools. Every other "
                    "address is counted only inside a group. It is not financial advice and it makes no forecast of price.")
    d.add_heading("The quarter in five points", 1)
    for x in FINDINGS:
        docx_rich(d.add_paragraph(style="List Number"), x)
    for i, s in enumerate(SECTIONS, 1):
        d.add_heading(f"{i}. {s['title']}", 1)
        p = d.add_paragraph(); docx_rich(p, s["answer"]); [setattr(r, "bold", True) for r in p.runs]
        blocks(s["blocks"])
    n = len(SECTIONS)
    d.add_heading(f"{n + 1}. Method: how to repeat this report", 1)
    blocks(METHOD)
    d.add_paragraph("To repeat it: set the quarter in scripts/fetch.py, run python3 scripts/fetch.py, then scripts/analyse.py, "
                    "scripts/build.py and scripts/check.py. METHOD.md in the repository gives every call in detail.")
    d.add_heading(f"{n + 2}. Sources and dates", 1)
    d.add_paragraph(f"Every figure is a balance or event on the Redbelly chain at block {num(F['start_block'])} ({START_AT}) or block "
                    f"{num(F['end_block'])} ({END_AT}), or an event between them. The data was read on {FETCHED}.")
    for t, u, w, dt in SOURCES:
        p = d.add_paragraph(style="List Bullet"); r = p.add_run(t + ". "); r.bold = True; p.add_run(w + f" {dt}. "); docx_link(p, u)
    d.add_heading(f"{n + 3}. The data", 1)
    p = d.add_paragraph("Every table is published as CSV at "); docx_link(p, f"{SITE}/#data")
    d.add_heading("Words used in this report", 1)
    for t, dfn in GLOSSARY:
        p = d.add_paragraph(style="List Bullet"); r = p.add_run(t + ": "); r.bold = True; p.add_run(dfn)
    cp = d.core_properties
    cp.title = TITLE; cp.subject = SUB; cp.author = "Redbelly DAO community research"; cp.last_modified_by = "Redbelly DAO community research"
    cp.comments = ""; cp.keywords = "RBNT, Redbelly, holders, staking, on-chain"
    cp.created = cp.modified = datetime(2026, 10, 17, tzinfo=timezone.utc); cp.revision = 1
    d.save(path)
    clean_app_props(path)

# ---------- Markdown ----------
def summary_md():
    out = ["# Community summary: RBNT holder report, Q3 2026", "", "Not financial advice. Every number comes from the full report: " + SITE, "",
           "## A few paragraphs", ""]
    for p in SUMMARY_PARAS:
        out += [p, ""]
    out += ["## As an X thread", ""]
    for i, p in enumerate(THREAD, 1):
        out += [f"**{i}/{len(THREAD)}** ({len(p)} characters)", "", p, ""]
    return "\n".join(out)

def render_pngs(specs):
    """Each chart as a PNG at 2x for the Word file, in the light palette."""
    from playwright.sync_api import sync_playwright
    out = {}
    fonts = (PUB / "fonts").as_uri()
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(device_scale_factor=2)
        for k, (_, _, svg) in specs.items():
            doc = (f'<!doctype html><html><head><style>@font-face{{font-family:"Be Vietnam Pro";src:url({fonts}/be-vietnam-pro-latin-400-normal.woff2)}}'
                   f'@font-face{{font-family:"JetBrains Mono";src:url({fonts}/jetbrains-mono-latin-400-normal.woff2)}}body{{margin:0;background:#fff}}'
                   f'svg{{display:block}}</style></head><body><div id="c" style="display:inline-block;padding:8px">{svg}</div></body></html>')
            pg.set_content(doc); pg.evaluate("document.fonts.ready.then(() => true)"); pg.wait_for_timeout(100)
            out[k] = BUILD / f"chart-{k}.png"; pg.locator("#c").screenshot(path=str(out[k]))
        b.close()
    return out

def make_og_image():
    from playwright.sync_api import sync_playwright
    fonts = (PUB / "fonts").as_uri(); logo = (PUB / "brand/dao-logo-on-dark.png").as_uri()
    stats = [(amt(F['staked_total_end']), "RBNT staked in the Reddex pools"), (num(F['holders_end_1plus']), "addresses with 1+ RBNT"),
             (pct(W['Redbelly reserved wallets']['end_pct']), "of RBNT in reserved wallets")]
    cells = "".join(f'<div class="d"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for v, l in stats)
    pg = (f'<!doctype html><html><head><meta charset="utf-8"><style>'
          f'@font-face{{font-family:"BV";src:url({fonts}/be-vietnam-pro-latin-700-normal.woff2);font-weight:700}}'
          f'@font-face{{font-family:"BV";src:url({fonts}/be-vietnam-pro-latin-400-normal.woff2);font-weight:400}}'
          f'@font-face{{font-family:"JM";src:url({fonts}/jetbrains-mono-latin-500-normal.woff2);font-weight:500}}'
          'html,body{margin:0}body{width:1200px;height:630px;background:#0c1317;color:#f1f5f8;font-family:BV,sans-serif;position:relative;overflow:hidden}'
          '.k{position:absolute;left:72px;top:70px;font:500 20px JM,monospace;letter-spacing:.08em;color:#a9b8c2;display:flex;align-items:center;gap:12px}'
          '.k i{width:12px;height:12px;border-radius:50%;background:#EF5350;display:inline-block}'
          'h1{position:absolute;left:72px;top:112px;width:900px;font-size:64px;line-height:1.06;letter-spacing:-.02em;margin:0}'
          '.p{position:absolute;left:72px;top:196px;font-size:26px;color:#c2ced6}'
          '.row{position:absolute;left:72px;right:72px;bottom:110px;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#263641;border:1px solid #263641;border-radius:8px;overflow:hidden}'
          '.d{background:#141f26;padding:22px 24px}.d b{display:block;font-size:40px;letter-spacing:-.01em}.d span{display:block;font-size:19px;color:#c2ced6;margin-top:6px}'
          '.n{position:absolute;left:72px;bottom:52px;font:500 17px JM,monospace;color:#8fa1ad}'
          'img{position:absolute;right:72px;top:56px;height:64px}</style></head><body>'
          f'<div class="k"><i></i>QUARTERLY ON-CHAIN REPORT</div><h1>RBNT holder report, Q3 2026</h1>'
          f'<div class="p">1 July to 30 September 2026, read from the Redbelly chain</div><div class="row">{cells}</div>'
          f'<div class="n">Last verified {FETCHED} · blocks {num(F["start_block"])} and {num(F["end_block"])} · not financial advice</div>'
          f'<img src="{logo}" alt=""></body></html>')
    tmp = BUILD / "og.html"; tmp.write_text(pg)
    with sync_playwright() as p:
        b = p.chromium.launch(); x = b.new_page(viewport={"width": 1200, "height": 630})
        x.goto(tmp.as_uri()); x.evaluate("document.fonts.ready.then(() => true)"); x.wait_for_timeout(300)
        x.screenshot(path=str(PUB / "brand/og.png")); b.close()

def main():
    BUILD.mkdir(exist_ok=True)
    for sub in ("downloads", "data", "charts"):
        (PUB / sub).mkdir(parents=True, exist_ok=True)
    number_figures()
    specs = chart_specs()
    for k, (_, _, svg) in specs.items():
        (PUB / "charts" / f"{k}.svg").write_text(svg)
    for f in sorted(DATA.glob("*.csv")) + [DATA / "figures.json"]:
        shutil.copy(f, PUB / "data" / f.name)
    shutil.copy(ROOT / "scripts/report.css", PUB / "report.css")
    (PUB / "index.html").write_text(home_page(specs))
    (PUB / "summary.html").write_text(summary_page())
    (PUB / "404.html").write_text(not_found_page())
    (BUILD / "print.html").write_text(print_page(specs))
    make_og_image()
    pngs = render_pngs(specs)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.goto((BUILD / "print.html").as_uri()); pg.evaluate("document.fonts.ready.then(() => true)"); pg.wait_for_timeout(500)
        pg.pdf(path=str(PUB / "downloads" / PDF_NAME), format="A4", print_background=True, outline=True, tagged=True,
               margin={"top": "14mm", "bottom": "16mm", "left": "0mm", "right": "0mm"}, display_header_footer=True,
               header_template="<span></span>",
               footer_template="<div style='font-family:sans-serif;font-size:8px;width:100%;padding:0 16mm;display:flex;justify-content:space-between;color:#4b5a64'>"
                               "<span>RBNT holder report, Q3 2026 · On-chain data, not financial advice</span><span><span class='pageNumber'></span> / <span class='totalPages'></span></span></div>")
        b.close()
    build_docx(PUB / "downloads" / DOCX_NAME, specs, pngs)
    (ROOT / "COMMUNITY-SUMMARY.md").write_text(summary_md()); shutil.copy(ROOT / "COMMUNITY-SUMMARY.md", PUB / "downloads/COMMUNITY-SUMMARY.md")
    shutil.copy(ROOT / "METHOD.md", PUB / "downloads/METHOD.md")
    print(f"built: {len(specs)} charts, {len(SECTIONS)} sections, thread posts {[len(p) for p in THREAD]}")

if __name__ == "__main__":
    main()
