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
        "outlook": {"q": "4Q26", "note": "Client SSD: limited increase; enterprise SSD +23-28%; NAND contract +15-20% QoQ (TrendForce, 2026-09-30)", "yoy_256gb": 303},
    },
    # ---------- 5. dated snapshot ----------
    "snapshot": [
        {"name": "DDR5 16Gb chip", "value": 61.50, "unit": "$", "as_of": "2026-10-30", "chg": 0.27,
         "src": "TrendForce DRAM spot (session average, +0.27% session change)"},
        {"name": "DDR4 16Gb chip", "value": 82.796, "unit": "$", "as_of": "2026-10-30", "chg": -0.15,
         "src": "TrendForce DRAM spot"},
        {"name": "512Gb TLC wafer", "value": 18.592, "unit": "$", "as_of": "2026-10-19", "chg": -1.28,
         "src": "TrendForce wafer spot"},
        {"name": "128Gb MLC contract", "value": 30.608, "unit": "$", "as_of": "2H Sep 2026", "chg": 0.44,
         "src": "TrendForce NAND contract"},
        {"name": "Client SSD 1TB contract", "value": 321.00, "unit": "$", "as_of": "3Q26", "chg": None,
         "src": "TrendForce PC-client OEM SSD contract, value grade"},
        {"name": "DDR5 32GB kit floor", "value": 446.41, "unit": "$", "as_of": "2026-10-31", "chg": None,
         "src": "RamRadar lowest tracked DDR5-6000 2x16GB kit"},
    ],
}


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

out = os.path.join(HERE, "dataset.json")
json.dump(ds, open(out, "w", encoding="utf-8"), separators=(",", ":"))
print("wrote", out, os.path.getsize(out), "bytes")
for k, s in ds["stats"].items():
    print(f"{k:12s} last {s['last']:>8} off_peak {s['off_peak_pct']:>7}%  30d {s['chg_30d']}%  "
          f"90d {s['chg_90d']}%  peak {s['peak']} on {s['peak_date']}")
