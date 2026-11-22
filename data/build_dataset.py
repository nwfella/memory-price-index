"""Build data/dataset.json for index.html from the harvested CSVs.

Every series keeps its source URL and observation dates so the page can cite it.
"""
import csv, json, datetime, os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.datetime.now(datetime.timezone.utc)


def rd(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- 1. retail RAM, daily $/GB (RamRadar) ----------
ram = rd("ramradar.csv")
by_day = defaultdict(dict)
for r in ram:
    if r["form_factor"] != "DIMM":
        continue
    by_day[r["date"]][r["ram_type"]] = {
        "avg": float(r["avg_price_per_gb"]) if r["avg_price_per_gb"] else None,
        "med": float(r["median_price_per_gb"]) if r["median_price_per_gb"] else None,
        "n": int(r["product_count"] or 0),
    }

days = sorted(by_day)


MIN_KITS = 10   # days with fewer tracked kits are too thin to quote


def retail(t, key="avg", min_kits=MIN_KITS):
    """Daily series; drops days with too few tracked kits to be meaningful."""
    out, kits = [], []
    for d in days:
        v = by_day[d].get(t)
        if v and v[key] is not None and v["n"] >= min_kits:
            out.append([d, round(v[key], 4)])
            kits.append([d, v["n"]])
    return out, kits


ddr5_avg, ddr5_n = retail("DDR5")
ddr4_avg, ddr4_n = retail("DDR4")
thin = {
    "min_kits": MIN_KITS,
    "ddr5_days_dropped": len([d for d in days if (by_day[d].get("DDR5") or {}).get("n", 0) < MIN_KITS]),
    "ddr4_days_dropped": len([d for d in days if (by_day[d].get("DDR4") or {}).get("n", 0) < MIN_KITS]),
}

# ---------- 2/3. TrendForce weekly spot quotes ----------
spot = rd("spot_series.csv")


def series(field, datefield):
    pts = []
    for r in spot:
        if r.get(field):
            pts.append([r.get(datefield) or r["article_date"], float(r[field]), r["url"]])
    pts.sort(key=lambda x: x[0])
    return pts


dram_spot = series("ddr4_mainstream_usd", "ddr4_date")   # DDR4 1Gx8 3200 (8Gb) chip, USD
nand_spot = series("nand512_tlc_usd", "nand_date")       # 512Gb TLC wafer, USD

ds = {
    "coverage": thin,
    "generated_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "as_of": days[-1],
    "series": {
        "ddr5_retail": {"label": "DDR5 desktop kit", "unit": "$/GB", "kind": "retail",
                        "pts": [[d, v] for d, v in ddr5_avg], "kits": ddr5_n,
                        "source": "RamRadar RAM Price Index",
                        "source_url": "https://ramradar.app/ram-price-index",
                        "note": "Daily mean asking price per GB across tracked DDR5 DIMM kits (eBay/Newegg lowest listed)."},
        "ddr4_retail": {"label": "DDR4 desktop kit", "unit": "$/GB", "kind": "retail",
                        "pts": [[d, v] for d, v in ddr4_avg], "kits": ddr4_n,
                        "source": "RamRadar RAM Price Index",
                        "source_url": "https://ramradar.app/ram-price-index",
                        "note": "Daily mean asking price per GB across tracked DDR4 DIMM kits."},
        "dram_spot": {"label": "DDR4 8Gb chip (spot)", "unit": "$/chip", "kind": "spot",
                      "pts": [[d, v] for d, v, _ in dram_spot],
                      "source": "TrendForce weekly memory spot update",
                      "source_url": "https://www.trendforce.com/price/dram/dram_spot",
                      "note": "Benchmark mainstream chip (DDR4 1Gx8 3200MT/s) average spot price, weekly quote."},
        "nand_spot": {"label": "512Gb TLC NAND wafer (spot)", "unit": "$/wafer", "kind": "spot",
                      "pts": [[d, v] for d, v, _ in nand_spot],
                      "source": "TrendForce weekly memory spot update",
                      "source_url": "https://www.trendforce.com/price/flash/wafer_spot",
                      "note": "512Gb TLC wafer average spot quotation, weekly."},
    },
    "source_posts": {d: u for d, v, u in dram_spot + nand_spot},
    # annotated discontinuities: drawn on the chart, never silently smoothed
    "marks": [
        {"date": "2026-05-29",
         "label": "listing-mix step: cheapest tracked DDR5 kit jumps $3.17 → $6.77/GB",
         "short": "listing-mix step",
         "keys": ["ddr5_retail", "ddr4_retail"]}
    ],
    # ---------- 4. client SSD contract, quarterly ----------
    "ssd_contract": {
        "unit": "$ per drive, OEM contract",
        "quarters": [
            {"q": "3Q25", "gb256": 33.30, "source": "TrendForce/DRAMeXchange via Notebookcheck, Oct 2026 (+303% YoY for 256GB TLC)"},
            {"q": "3Q26", "gb256": 128.38, "gb512": 201.13, "gb1t": 321.00,
             "source": "TrendForce PC-Client OEM SSD Contract Price, 3Q26 (published 2026-08-05)"},
        ],
    },
    # ---------- 5. forward guidance, dated and attributed ----------
    # Each line is a print we can link to. Superseded prints stay listed with their
    # date so the page shows a direction of travel, not a single frozen number.
    "guidance": [
        {"date": "2026-11-19", "tag": "NAND contract",
         "note": "4Q26 increase cut to <b>+8–13% QoQ</b> (from +15–20% on 30 Sep). 1Q27 <b>−0–5% QoQ</b>, with every product category in a down-cycle from 2Q27; 2027 bit supply +25–30% YoY.",
         "url": "https://www.trendforce.com/presscenter/news/20261119-13314.html"},
        {"date": "2026-11-11", "tag": "PC DRAM contract",
         "note": "<b>+13–18% QoQ</b> in 4Q26 — still rising, but slower than 3Q26. Suppliers tentatively plan to cut PC DRAM supply in 2027.",
         "url": "https://www.trendforce.com/presscenter/news/20261111-13303.html"},
        {"date": "2026-11-11", "tag": "Client SSD contract",
         "note": "<b>Under +5% QoQ</b> in 4Q26 — a hard deceleration from the +285–303% YoY of 3Q26. OEMs are buying only what production needs.",
         "url": "https://www.trendforce.com/presscenter/news/20261111-13303.html"},
        {"date": "2026-11-11", "tag": "Demand",
         "note": "Notebook shipments <b>−15.8% QoQ in 3Q26</b>, with a further decline guided for 4Q26; finished-goods inventory is building and 1Q27 procurement plans are being revised down.",
         "url": "https://www.trendforce.com/presscenter/news/20261111-13303.html"},
        {"date": "2026-09-30", "tag": "Conventional DRAM contract",
         "note": "+10–15% QoQ for 4Q26 (superseded for PC DRAM by the 11 Nov print).",
         "url": "https://www.trendforce.com/presscenter/news/20260930-13258.html"},
    ],
}


# ---------- 6. dated snapshot: live spot boards + contract prints ----------
# The boards expose only the current session, so they are re-read on every build
# (data/fetch_spot_board.py). Curated to benchmark parts; every row carries the
# board's own update timestamp, so a stale board shows its age instead of lying.
BOARD_PICKS = [
    ("dram_spot", "DDR5 16Gb (2Gx8) 4800/5600", "DDR5 16Gb chip"),
    ("dram_spot", "DDR5 16Gb (2Gx8) eTT", "DDR5 16Gb eTT"),
    ("dram_spot", "DDR4 16Gb (2Gx8) 3200", "DDR4 16Gb chip"),
    ("dram_spot", "DDR4 8Gb (1Gx8) 3200", "DDR4 8Gb chip"),
    ("dram_spot", "DDR4 8Gb (1Gx8) eTT", "DDR4 8Gb eTT"),
    ("nand_wafer", "512Gb TLC", "512Gb TLC wafer"),
    ("nand_wafer", "256Gb TLC", "256Gb TLC wafer"),
    ("nand_wafer", "128Gb TLC", "128Gb TLC wafer"),
    ("nand_wafer", "MLC 64Gb 8GBx8", "MLC 64Gb wafer"),
]


def snapshot():
    rows = []
    try:
        board = json.load(open(os.path.join(HERE, "spot_board.json"), encoding="utf-8"))
    except Exception:
        board = {"boards": []}
    by_id = {b["id"]: b for b in board.get("boards", [])}
    for bid, part, label in BOARD_PICKS:
        b = by_id.get(bid)
        if not b:
            continue
        row = next((r for r in b["rows"] if r["name"] == part), None)
        if not row:
            continue
        rows.append({"name": label, "value": row["value"], "unit": "$",
                     "as_of": (b.get("as_of") or "")[:16] or "n/a",
                     "chg": row.get("chg"),
                     "src": "%s board — session average%s" % (
                         "DRAM spot" if bid == "dram_spot" else "NAND wafer spot",
                         "" if not b.get("stale") else " (board did not refresh; last good read)")})
    # contract prints: no live session, so they carry their own period
    rows += [
        {"name": "128Gb MLC contract", "value": 30.608, "unit": "$", "as_of": "2H Sep 2026",
         "chg": 0.44, "src": "TrendForce NAND contract"},
        {"name": "Client SSD 1TB contract", "value": 321.00, "unit": "$", "as_of": "3Q26",
         "chg": None, "src": "TrendForce PC-client OEM SSD contract, value grade"},
    ]
    # kit floor: lowest tracked DDR5 kit, converted to a 32GB (2x16) drive-out
    try:
        last = days[-1]
        floor = float([r for r in ram if r["date"] == last and r["ram_type"] == "DDR5"
                       and r["form_factor"] == "DIMM"][0]["min_price_per_gb"])
        rows.append({"name": "DDR5 32GB kit floor", "value": round(floor * 32, 2), "unit": "$",
                     "as_of": last, "chg": None,
                     "src": "RamRadar cheapest tracked DDR5 DESKTOP kit × 32GB"})
    except Exception:
        pass
    return rows


ds["snapshot"] = snapshot()


def stats(pts):
    """peak / last / drawdown / window changes for one series."""
    if not pts:
        return {}
    vals = [p[1] for p in pts]
    last = vals[-1]
    peak = max(vals)
    peak_date = pts[vals.index(peak)][0]
    out = {"first": vals[0], "first_date": pts[0][0], "last": last, "last_date": pts[-1][0],
           "peak": peak, "peak_date": peak_date,
           "off_peak_pct": round((last / peak - 1) * 100, 2),
           "since_first_pct": round((last / vals[0] - 1) * 100, 2)}

    def back(days_):
        cutoff = (datetime.date.fromisoformat(pts[-1][0]) - datetime.timedelta(days=days_)).isoformat()
        cand = [p for p in pts if p[0] <= cutoff]
        if not cand:
            return None
        return round((last / cand[-1][1] - 1) * 100, 2)

    for label, d in (("7d", 7), ("30d", 30), ("90d", 90), ("365d", 365)):
        out["chg_" + label] = back(d)
    return out


ds["stats"] = {k: stats(v["pts"]) for k, v in ds["series"].items()}

# A series that lost its history is a data problem, not a reason to ship a blank
# page: say which one is short and keep going (the map-style KeyError that froze
# this site for four days in Nov 2026 came from exactly this line).
short = [k for k, s in ds["stats"].items() if len(s) < 3]
if short:
    print("WARN: series with no usable history:", ", ".join(short))

out = os.path.join(HERE, "dataset.json")
json.dump(ds, open(out, "w", encoding="utf-8"), separators=(",", ":"))
print("wrote", out, os.path.getsize(out), "bytes")
for k, s in ds["stats"].items():
    if not s:
        print(f"{k:12s} EMPTY — no priced observations")
        continue
    print(f"{k:12s} last {s['last']:>8} off_peak {s['off_peak_pct']:>7}%  "
          f"30d {s['chg_30d']}%  90d {s['chg_90d']}%  peak {s['peak']} on {s['peak_date']}")

