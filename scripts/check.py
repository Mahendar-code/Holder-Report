#!/usr/bin/env python3
"""Quality gate for the report. Ends with RESULT: PASS or RESULT: FAIL.

  python3 scripts/check.py           checks the built outputs
  python3 scripts/check.py --online  also re-reads a sample of figures from the Redbelly RPC
"""
import csv, json, re, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB, DATA = ROOT / "public", ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))
FAIL = []

def check(ok, msg):
    print(("ok    " if ok else "FAIL  ") + msg)
    if not ok:
        FAIL.append(msg)

F = json.loads((DATA / "figures.json").read_text())
NAMED = {w["address"].lower() for w in json.loads((ROOT / "content/named_wallets.json").read_text())}
NAMED |= {a.lower() for a in F["labelled_on_routescan"]}
PDF = next((PUB / "downloads").glob("*.pdf")); DOCX = next((PUB / "downloads").glob("*.docx"))

def pdf_text():
    return subprocess.run(["pdftotext", "-layout", str(PDF), "-"], capture_output=True, text=True).stdout

def docx_text():
    with zipfile.ZipFile(DOCX) as z:
        xml = z.read("word/document.xml").decode()
    return re.sub(r"<[^>]+>", " ", xml)

def docx_props():
    with zipfile.ZipFile(DOCX) as z:
        return z.read("docProps/core.xml").decode() + z.read("docProps/app.xml").decode()

texts = {p.relative_to(ROOT).as_posix(): p.read_text() for p in list(PUB.glob("*.html")) + [ROOT / "COMMUNITY-SUMMARY.md", ROOT / "METHOD.md",
         ROOT / "README.md"] + list(DATA.glob("*.csv")) + [DATA / "figures.json"] + list((PUB / "charts").glob("*.svg")) + list((ROOT / "evidence").glob("*")) if p.exists()}
texts["PDF"] = pdf_text(); texts["Word"] = docx_text()
prose = {k: v for k, v in texts.items() if not k.endswith((".csv", ".json"))}

# 1. the data adds up
for k, v in F["checks"].items():
    check(abs(v) < 1e-6, f"data check is zero: {k} ({v:.6f})")

# 2. no address other than a named one, anywhere
ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
for name, t in texts.items():
    other = {a.lower() for a in ADDR.findall(t)} - NAMED
    check(not other, f"{name}: only named addresses appear" + (f" (found {len(other)} other)" if other else ""))

# 3. no group of fewer than 5 holders
for name, b in F["bands"].items():
    for t in ("start", "end"):
        check(b[t] == 0 or b[t] >= 5, f"band '{name}' at {t} has 5 or more holders ({b[t]})")
for name, c in F["cohorts"].items():
    check(c["holders"] >= 5, f"rank group '{name}' has 5 or more holders")

# 4. no forecast, advice or calls to trade; no hype
BAD = re.compile(r"\b(buy|buying|bullish|bearish|pump|dump|moon|price target|undervalued|overvalued|will rise|will fall|should (buy|sell|hold)|"
                 r"invest(ing)? in|good time to|opportunity|forecast(s|ing)? (that|a)|expect(ed)? to (rise|fall|grow)|elevate|seamless|unleash|revolutioni[sz]e)\b", re.I)
for name, t in prose.items():
    hits = sorted({m.group(0).lower() for m in BAD.finditer(re.sub(r"<[^>]+>", " ", t))})
    check(not hits, f"{name}: no advice, forecast or hype words" + (f" {hits}" if hits else ""))
for name in ("public/index.html", "PDF", "Word", "COMMUNITY-SUMMARY.md"):
    t = re.sub(r"\s+", " ", prose[name])
    check("not financial advice" in t.lower(), f"{name}: says it is not financial advice")
    if name != "COMMUNITY-SUMMARY.md":
        check("may include reward funds as well as stakes" in t, f"{name}: says a pool balance may include reward funds")
        check("WRBNT" in t and "counted once" in t, f"{name}: says WRBNT is counted once")

# 5. brand voice: no en dash, em dash or emoji
for name, t in prose.items():
    check(not re.search("[–—]", t), f"{name}: no en or em dash")
    check(not re.search("[\U0001F300-\U0001FAFF☀-➿]", t), f"{name}: no emoji")

# 6. no personal credit
creds = []
for f in (".credit-names", ".credit-links"):
    p = ROOT / f
    if p.exists():
        creds += [l.strip().lower() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
check(bool(creds), "credit lists are present to scan against")
allt = "\n".join(texts.values()).lower() + docx_props().lower()
for c in creds:
    check(c not in allt, f"no personal credit: '{c[:2]}...' not found")
props = docx_props()
check(not re.search(r"python|docx|claude|anthropic|openai|gpt", props, re.I), "Word file properties name no tool or person")

# 7. community summary
import build
for i, p in enumerate(build.THREAD, 1):
    check(len(p) <= 280, f"X post {i} is 280 characters or fewer ({len(p)})")

# 8. every number in the five points and section answers is in the web page, the PDF and the Word file
norm = {k: re.sub(r"\s+", " ", v) for k, v in prose.items()}
for name in ("public/index.html", "PDF", "Word"):
    missing = sorted({n for t in build.FINDINGS + [s["answer"] for s in build.SECTIONS]
                      for n in re.findall(r"\d[\d,]*(?:\.\d+)?%?", build.plain(t)) if n not in norm[name]})
    check(not missing, f"{name} carries every number in the findings and answers" + (f" (missing {missing})" if missing else ""))

# 9. the web page loads nothing from another domain, and every local link resolves
for p in PUB.glob("*.html"):
    h = p.read_text()
    check(not [u for u in re.findall(r'<(?:script|img)[^>]+src="(https?://[^"]+)"', h)] and
          not re.findall(r'<link[^>]+rel="stylesheet"[^>]+href="https?://', h), f"{p.name}: loads nothing from another domain")
    for href in re.findall(r'href="(/?[^"#:]+)(?:#[^"]*)?"', h):
        target = PUB / href.lstrip("/")
        ok = target.exists() or (target.with_suffix(".html")).exists() or href in ("/",)
        check(ok, f"{p.name}: link {href} resolves")
    for anchor in re.findall(r'href="/?#([^"]+)"', h):
        idx = (PUB / "index.html").read_text()
        check(f'id="{anchor}"' in idx, f"{p.name}: anchor #{anchor} exists")

# 10. published data equals the analysis output
for f in list(DATA.glob("*.csv")) + [DATA / "figures.json"]:
    check((PUB / "data" / f.name).read_bytes() == f.read_bytes(), f"public/data/{f.name} matches data/{f.name}")

# 11. optional: re-read a sample from the chain
if "--online" in sys.argv:
    import fetch
    E = 10 ** 18
    for a, d in list(F["named"].items()):
        got = fetch.rpc_batch([("eth_getBalance", [a, hex(F["start_block"])]), ("eth_getBalance", [a, hex(F["end_block"])])])
        check(abs(int(got[0], 16) / E - d["start"]) < 1e-6 and abs(int(got[1], 16) / E - d["end"]) < 1e-6, f"chain agrees on {d['name']}")
    for a, p in F["pools"].items():
        got = fetch.rpc_batch([("eth_call", [{"to": a, "data": "0x8b0e9f3f"}, hex(F["end_block"])])])
        check(abs(int(got[0], 16) / E - p["stake_end"]) < 0.01, f"chain agrees on totalStake of {p['name']}")

print(f"\n{len(FAIL)} failed")
print("RESULT: " + ("PASS" if not FAIL else "FAIL"))
sys.exit(1 if FAIL else 0)
