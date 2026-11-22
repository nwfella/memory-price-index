"""Fetch the live TrendForce spot-price boards -> data/spot_board.json.

The boards only ever show the *current* session; that is exactly what the page's
"Spot board" section needs, so it is re-read at build time instead of being a
hand-copied block that silently ages (the previous hardcoded snapshot was five
weeks stale by the time anyone noticed).

Output shape:
  {"fetched_at": iso, "boards": [
     {"id": "dram_spot", "label": "DRAM spot", "as_of": "2026-11-20 18:10 (GMT+8)",
      "unit": "$/chip", "source_url": "...",
      "rows": [{"name": "DDR4 8Gb (1Gx8) 3200", "value": 43.75, "chg": -0.39}, ...]}, ...]}

Failure policy: never clobber a good file. If a board cannot be fetched or parses
to zero rows, the previous spot_board.json is left untouched and the build falls
back to it (the page then shows the older date, which is honest).
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "spot_board.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")

BOARDS = [
    {"id": "dram_spot", "label": "DRAM spot", "unit": "$/chip",
     "url": "https://www.trendforce.com/price/dram/dram_spot"},
    {"id": "nand_wafer", "label": "NAND wafer spot", "unit": "$/wafer",
     "url": "https://www.trendforce.com/price/flash/wafer_spot"},
]


def ssl_context():
    """Prefer a full CA bundle: some conda installs ship a stale SSL_CERT_FILE that
    breaks DigiCert chains with 'self-signed certificate in certificate chain'."""
    for mod in ("certifi",):
        try:
            import importlib
            ca = importlib.import_module(mod).where()
            return ssl.create_default_context(cafile=ca)
        except Exception:
            pass
    return ssl.create_default_context()


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40, context=ssl_context()) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:                       # TLS/DNS blips are intermittent here
            last = e
            time.sleep(2 + 3 * i)
    raise last


def txt(cell):
    cell = re.sub(r"<[^>]+>", "", cell)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&#39;", "'")):
        cell = cell.replace(a, b)
    return re.sub(r"\s+", " ", cell).strip()


def parse_board(html, board):
    as_of = re.search(r"Last Update\s*([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]+ \(GMT[+-][0-9]+\))", html)
    rows = []
    for block in re.findall(r"<tr>(.*?)</tr>", html, re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", block, re.S | re.I)
        if len(tds) < 6:
            continue
        name = txt(tds[0])
        if not name or len(name) > 80:
            continue
        nums = [txt(t) for t in tds[1:]]
        vals = []
        for n in nums:
            try:
                vals.append(float(n))
            except ValueError:
                vals.append(None)
        # columns: daily/weekly high, low, session high, session low, session average
        priced = [v for v in vals if v is not None]
        if len(priced) < 5:
            continue
        avg = vals[4] if vals[4] is not None else priced[-1]
        pct_cell = next((t for t in tds[1:] if "-trend" in t.lower() or "%" in t), "")
        chg = 0.0 if re.search(r"0\.00\s*%", txt(pct_cell)) else None
        m = re.search(r"(rise|fall)-trend", pct_cell, re.I)
        num = re.search(r"(-?[0-9.]+)\s*%", txt(pct_cell))
        if num:
            chg = float(num.group(1))
            if not num.group(1).startswith("-") and m:      # unsigned numeral: take the arrow's sign
                chg = -abs(chg) if m.group(1).lower() == "fall" else abs(chg)
        rows.append({"name": name, "value": round(avg, 3), "chg": chg})
    return {"id": board["id"], "label": board["label"], "unit": board["unit"],
            "source_url": board["url"], "as_of": as_of.group(1) if as_of else None,
            "rows": rows}


def main():
    prev = {}
    if os.path.exists(OUT):
        try:
            prev = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            prev = {}

    out = {"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "boards": []}
    ok = 0
    for board in BOARDS:
        old = next((b for b in prev.get("boards", []) if b.get("id") == board["id"]), None)
        try:
            parsed = parse_board(get(board["url"]), board)
        except Exception as e:
            parsed = {"id": board["id"], "label": board["label"], "unit": board["unit"],
                      "source_url": board["url"], "as_of": None, "rows": [], "err": str(e)[:100]}
        if len(parsed["rows"]) >= 2:
            ok += 1
            print(f"  {board['id']}: {len(parsed['rows'])} rows, as of {parsed['as_of']}")
        else:
            print(f"  {board['id']}: FETCH/PARSE FAILED ({parsed.get('err') or 'no rows'})")
            if old:                                  # keep the last good board rather than blank it
                old = dict(old)
                old["stale"] = True
                parsed = old
                print(f"  {board['id']}: kept last good board (as of {old.get('as_of')})")
        out["boards"].append(parsed)

    if ok == 0 and prev.get("boards"):
        print("  spot board: no board refreshed — keeping previous spot_board.json")
        return 0
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"  wrote {os.path.basename(OUT)} ({ok}/{len(BOARDS)} boards live)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
