"""One-command refresh: pull fresh sources, rebuild the dataset, rebuild index.html.

    python data/refresh.py

steps
  1. re-download the RamRadar daily RAM index CSV
  2. discover new weekly spot posts on TrendForce's news search and merge them into spot_urls.txt
  3. re-fetch + re-parse every post in spot_urls.txt (TrendForce revises old posts, so re-parse all)
  4. rebuild data/dataset.json  (stats, drawdown, marks)
  5. rebuild index.html         (data baked in — the page never fetches at runtime)

Discovery only sees the most recent results page, so it catches new weeks; the URL list stays the
durable record of what has been parsed.
"""
import os, re, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
RAMRADAR = "https://ramradar.app/ram-price-index/data.csv"


def step(msg):
    print("\n== " + msg)


def run(script):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        sys.exit("FAILED: " + script)
    lines = [l for l in r.stdout.strip().split("\n") if l.strip()]
    for l in lines[:6]:
        print("   " + l)
    if len(lines) > 6:
        print("   ... " + lines[-1])


step("1/5  downloading RamRadar daily index")
req = urllib.request.Request(RAMRADAR, headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=60) as r:
    body = r.read()
if len(body) < 10000 or b"date,ram_type" not in body[:200]:
    sys.exit("RamRadar CSV looks wrong (%d bytes) — refusing to overwrite" % len(body))
open(os.path.join(HERE, "ramradar.csv"), "wb").write(body)
print("   %d bytes, %d rows" % (len(body), body.count(b"\n")))

step("2/5  discovering new weekly spot posts")
URLS = os.path.join(HERE, "spot_urls.txt")
known = {u.strip().rstrip("/") for u in open(URLS, encoding="utf-8") if u.strip()}
try:
    page = urllib.request.urlopen(urllib.request.Request(
        "https://www.trendforce.com/news/?s=memory+spot+price+update",
        headers={"User-Agent": UA}), timeout=40).read().decode("utf-8", "replace")
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

step("3/5  re-parsing TrendForce weekly spot posts")
run("fetch_spot_quotes.py")

step("4/5  building dataset")
run("build_dataset.py")

step("5/5  building index.html")
run("build.py")

print("\nDone. Commit index.html (+ data/dataset.json) to publish.")
