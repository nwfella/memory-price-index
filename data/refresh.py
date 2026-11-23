"""One-command refresh: pull fresh sources, rebuild the dataset, rebuild index.html.

    python data/refresh.py

steps
  1. re-download the RamRadar daily RAM index CSV      (hard fail: retail is the core series)
  2. re-read the live TrendForce spot boards           (soft: keeps the last good board)
  3. discover new weekly spot posts on TrendForce's news search and merge them into spot_urls.txt
  4. re-fetch + re-parse every post in spot_urls.txt   (soft: keeps the last good spot history)
  5. rebuild data/dataset.json  (stats, drawdown, marks)
  6. rebuild index.html         (data baked in — the page never fetches at runtime)

The soft steps matter: TrendForce fails intermittently from this network (TLS chain
errors, DNS blips). A spot outage must not freeze the retail series — in Nov 2026 the
build died on an empty spot table before retail could reach the page, and the site sat
stale for four days.

Discovery only sees the most recent results page, so it catches new weeks; the URL list stays the
durable record of what has been parsed.
"""
import os, re, ssl, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
RAMRADAR = "https://ramradar.app/ram-price-index/data.csv"


def step(msg):
    print("\n== " + msg)


def ctx():
    """Prefer certifi: a stale conda SSL_CERT_FILE fails DigiCert chains outright."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch(url, timeout=60, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx()) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(3 + 4 * i)
    raise last


def run(script, required=True):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-1500:]); print(r.stderr[-1500:])
        if required:
            sys.exit("FAILED: " + script)
        print("   [soft] %s failed — continuing with the stored data" % script)
        return False
    lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
    for l in lines[:6]:
        print("   " + l)
    if len(lines) > 6:
        print("   ... " + lines[-1])
    return True


def merge_ramradar(path, body):
    """Union the fresh download into the stored CSV; the download always wins.

    RamRadar serves a **rolling window** (~170 days), not a full series: on 18 Nov 2026
    its export silently shrank from 392 days to 172, and a wholesale overwrite threw
    away seven months of retail history that the chart had already shown. Keep every
    day we have ever seen, let today's rows overwrite the same keys, and sort for a
    stable diff.
    """
    import csv
    rows = {}
    header = None
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            header = rdr.fieldnames
            for r in rdr:
                rows[(r["date"], r["ram_type"], r["form_factor"])] = r
    kept = len(rows)

    text = body.decode("utf-8-sig", "replace")
    rdr = csv.DictReader(text.splitlines())
    new_header = rdr.fieldnames or header
    incoming, incoming_days = 0, set()
    for r in rdr:
        if not r.get("date"):
            continue
        rows[(r["date"], r["ram_type"], r["form_factor"])] = r
        incoming += 1
        incoming_days.add(r["date"])
    if not incoming:
        raise SystemExit("RamRadar CSV parsed to zero rows — refusing to touch the stored file")

    header = header or new_header
    out = sorted(rows.values(), key=lambda r: (r["date"], r["ram_type"], r["form_factor"]))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    all_days = {r["date"] for r in out}
    return len(incoming_days), len(all_days - incoming_days), len(all_days)


step("1/6  downloading RamRadar daily index")
body = fetch(RAMRADAR)
if len(body) < 10000 or b"date,ram_type" not in body[:200]:
    sys.exit("RamRadar CSV looks wrong (%d bytes) — refusing to overwrite" % len(body))
kept, carried, days = merge_ramradar(os.path.join(HERE, "ramradar.csv"), body)
print("   %d rows downloaded (%d days); stored file now %d days — %d carried over from earlier exports"
      % (len(body.splitlines()) - 1, kept, days, carried))

step("2/6  reading live TrendForce spot boards")
run("fetch_spot_board.py", required=False)

step("3/6  discovering new weekly spot posts")
URLS = os.path.join(HERE, "spot_urls.txt")
known = {u.strip().rstrip("/") for u in open(URLS, encoding="utf-8") if u.strip()}
try:
    page = fetch("https://www.trendforce.com/news/?s=memory+spot+price+update",
                 timeout=40, tries=2).decode("utf-8", "replace")
    found = {m.rstrip("/") for m in re.findall(
        r'href="(https://www\.trendforce\.com/news/20\d{2}/\d{2}/\d{2}/[a-z0-9-]*spot-price[a-z0-9-]*)/?"',
        page)}
    new = sorted(found - known)
    if new:
        with open(URLS, "a", encoding="utf-8", newline="\n") as f:
            for u in new:
                f.write(u + "\n")
    print("   %d on search page, %d new -> %d total" % (len(found), len(new), len(known) + len(new)))
except Exception as e:
    print("   discovery skipped (%s) — continuing with the stored list" % str(e)[:60])

step("4/6  re-parsing TrendForce weekly spot posts")
run("fetch_spot_quotes.py", required=False)

step("5/6  building dataset")
run("build_dataset.py")

step("6/6  building index.html")
run("build.py")

print("\nDone. Commit index.html (+ data/dataset.json) to publish.")
