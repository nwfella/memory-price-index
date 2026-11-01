"""Fetch + parse TrendForce weekly spot-price posts (absolute quotes).

Outputs spot_series.csv with, per post:
  obs_date, ddr4_mainstream_usd, nand512_tlc_usd, source_url

Parsing rules learned from the actual article text:
  "... mainstream chips (i.e., DDR4 1Gx8 3200MT/s) has increased by 0.55% from
   US$46.79 last week (October 21) to US$47.04 this week (October 27)."
  -> the CURRENT value is the one immediately followed by "this week (Month D)".
  "Spot prices of 512Gb TLC wafers dropped by 9.19% this week (October 26),
   with average quotations arriving at US$16.883."
"""
import re, json, csv, urllib.request, os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=35) as r:
        return r.read().decode("utf-8", "replace")


def clean(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#39;", "'")
    return re.sub(r"\s+", " ", t)


def parse(url):
    try:
        return _parse(url)
    except Exception as e:
        return {"url": url, "article_date": None, "obs_date": None, "ddr4_mainstream_usd": None,
                "nand512_tlc_usd": None, "ddr4_pct_change": None, "nand_pct_change": None,
                "title": "", "err": "PARSE:" + str(e)[:80], "nand_ctx": "", "ddr4_ctx": ""}


ISO_DATE = r"([A-Z][a-z]+) (\d{1,2})"


def _sentence_around(txt, idx, span=320):
    """Text from idx forward to the next full stop (capped at span chars)."""
    chunk = txt[idx:idx + span]
    dot = chunk.find(". ")
    return chunk[:dot + 1] if dot > 20 else chunk


def _money_in(s):
    """Pick the CURRENT-week figure out of a sentence."""
    for pat in (
        r"to\s+US\$(\d+(?:\.\d+)?)\s+this week",          # "from US$x last week to US$y this week"
        r"US\$(\d+(?:\.\d+)?)\s+this week",               # "to US$y this week"
        r"quotations arriving at US\$(\d+(?:\.\d+)?)",    # NAND phrasing
        r"arriving at US\$(\d+(?:\.\d+)?)",
        r"to\s+US\$(\d+(?:\.\d+)?)",
    ):
        m = re.search(pat, s)
        if m:
            return float(m.group(1))
    amounts = re.findall(r"US\$(\d+(?:\.\d+)?)", s)
    return float(amounts[-1]) if amounts else None


def _week_date(s, year):
    m = re.search(r"this week\s*\(" + ISO_DATE + r"\)", s) or re.search(r"\(" + ISO_DATE + r"\)", s)
    if m and MONTHS.get(m.group(1)):
        return f"{year}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"
    return None


def _parse(url):
    art = re.search(r"/news/(\d{4})[-/](\d{2})[-/](\d{2})/", url)
    row = {"url": url,
           "article_date": f"{art.group(1)}-{art.group(2)}-{art.group(3)}" if art else None,
           "ddr4_date": None, "nand_date": None, "obs_date": None,
           "ddr4_mainstream_usd": None, "nand512_tlc_usd": None,
           "ddr4_pct_change": None, "nand_pct_change": None,
           "title": "", "err": None, "ddr4_ctx": "", "nand_ctx": ""}
    try:
        html = get(url)
    except Exception as e:
        row["err"] = str(e)[:120]
        return row

    t = clean(html)
    y = int(row["article_date"][:4]) if row["article_date"] else 2026
    title = re.search(r'"headline"\s*:\s*"([^"]+)"', html) or re.search(r"<title>([^<]+)", html)
    row["title"] = (title.group(1) if title else "")[:120]

    # ---- DDR4 mainstream chip: anchor on the benchmark sentence ----
    for anchor in ("mainstream chips", "mainstream DDR4", "DDR4 1Gx8 3200"):
        idx = t.find(anchor)
        if idx < 0:
            continue
        s = _sentence_around(t, idx)
        val = _money_in(s)
        if val and 3 < val < 200:
            row["ddr4_mainstream_usd"] = val
            row["ddr4_date"] = _week_date(s, y)
            row["ddr4_ctx"] = s[:240]
            pcm = re.search(r"(-?\d+(?:\.\d+)?)%", s)
            if pcm:
                row["ddr4_pct_change"] = float(pcm.group(1))
            break

    # ---- 512Gb TLC wafer spot: first occurrence that actually carries a price ----
    for m in re.finditer(r"512Gb TLC", t):
        s = _sentence_around(t, m.start())
        val = _money_in(s)
        if val and 0.5 < val < 60:
            row["nand512_tlc_usd"] = val
            row["nand_date"] = _week_date(s, y)
            row["nand_ctx"] = s[:240]
            pcm = re.search(r"(-?\d+(?:\.\d+)?)%", s)
            if pcm:
                row["nand_pct_change"] = float(pcm.group(1))
            break

    row["obs_date"] = row["ddr4_date"] or row["nand_date"] or row["article_date"]
    return row


if __name__ == "__main__":
    urls = [u.strip() for u in open("spot_urls.txt", encoding="utf-8") if u.strip()]
    # normalise: force https + www + trailing slash, fix YYYY-MM-DD style dates
    norm = []
    for u in urls:
        u = u.replace("http://", "https://")
        u = re.sub(r"https://trendforce\.com", "https://www.trendforce.com", u)
        u = re.sub(r"/news/(\d{4})-(\d{2})-(\d{2})/", r"/news/\1/\2/\3/", u)
        if not u.endswith("/"):
            u += "/"
        norm.append(u)
    norm = sorted(set(norm))
    print(f"{len(norm)} urls")
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(parse, norm))
    rows = [r for r in rows if not r["err"] or r["ddr4_mainstream_usd"] or r["nand512_tlc_usd"]]
    rows.sort(key=lambda r: r["obs_date"] or "")
    with open("spot_series.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["obs_date", "ddr4_date", "nand_date", "article_date", "ddr4_mainstream_usd",
                                          "ddr4_pct_change", "nand512_tlc_usd",
                                          "nand_pct_change", "url", "title"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in w.fieldnames})
    json.dump(rows, open("spot_posts.json", "w", encoding="utf-8"), indent=1)
    print(f"{sum(1 for r in rows if r['ddr4_mainstream_usd'])} DDR4 points, "
          f"{sum(1 for r in rows if r['nand512_tlc_usd'])} NAND points")
    for r in rows:
        print(f"{r['obs_date']}  DDR4 ${r['ddr4_mainstream_usd'] or '-':>8}  "
              f"NAND512 ${r['nand512_tlc_usd'] or '-':>8}  {r['title'][:50]}")
