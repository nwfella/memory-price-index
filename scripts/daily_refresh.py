#!/usr/bin/env python3
"""Daily Memwatch refresh: pull sources -> rebuild -> gate -> commit + push -> verify live.

Designed for a no_agent Hermes cron job: STDOUT IS THE DELIVERED REPORT.
One short line per run; a non-zero exit raises a scheduler alert.

Guards (see skill cron-python-execution-on-windows):
  * refuse to build from a dirty *source* tree (generated files excluded)
  * if the TrendForce spot re-parse degrades, fall back to the last good spot_series.csv
    so a bad upstream day cannot wipe 12 months of history off the chart
  * skip commit/push when the material data is unchanged (timestamps excluded)
  * git with a frozen, never-prompting env + tree-killing timeouts; retry only network errors

Usage:
    python scripts/daily_refresh.py            # normal run
    python scripts/daily_refresh.py --dry-run  # do everything, restore tree, report only
    python scripts/daily_refresh.py --force    # push even if data is unchanged (first-run test)
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
PY = sys.executable
BRANCH = "main"
LIVE = "https://nwfella.github.io/memory-price-index/"
GENERATED = ["index.html", "data/dataset.json"]
RAW = ["data/ramradar.csv", "data/spot_series.csv", "data/spot_posts.json", "data/spot_urls.txt"]
SOURCES = ["template.html", "data/build.py", "data/build_dataset.py",
           "data/fetch_spot_quotes.py", "data/refresh.py", "scripts"]
MIN_SPOT_ROWS = 30          # a healthy re-parse yields 37 priced weekly quotes
TRANSIENT = re.compile(
    r"could not resolve host|connection (?:timed out|reset|refused)|failed to connect"
    r"|remote end hung up|early eof|rpc failed|timed out|ssl", re.I)

DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv


def log(msg):
    print(msg, flush=True)


def die(msg, code=1):
    print(msg, flush=True)
    sys.exit(code)


def _env():
    e = os.environ.copy()
    e.pop("PYTHONPATH", None)
    e.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never",
              "GIT_ASKPASS": "", "GIT_CONFIG_PARAMETERS": "'credential.interactive=false'"})
    return e


def run(cmd, timeout=180, cwd=REPO):
    """Tree-killing timeout + an environment that can never open a credential dialog."""
    p = subprocess.Popen(cmd, cwd=cwd, env=_env(), text=True,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    try:
        out, err = p.communicate(timeout=timeout)
        return p.returncode, out or "", err or ""
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        try:
            out, err = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return -1, out or "", ((err or "") + "\nTIMEOUT after %ss (tree killed)" % timeout).strip()


def git(*args, timeout=180):
    return run(["git"] + list(args), timeout=timeout)


def tail(text, n=6):
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def signature(ds):
    """Material-data fingerprint: identical data must not create a commit."""
    clone = json.loads(json.dumps(ds))
    clone.pop("generated_at", None)
    return hashlib.sha256(json.dumps(clone, sort_keys=True).encode()).hexdigest()


def head_signature():
    rc, out, _ = git("show", "HEAD:data/dataset.json")
    if rc != 0 or not out.strip():
        return None
    try:
        return signature(json.loads(out))
    except Exception:
        return None


def live_matches(local_bytes, budget=150):
    """Poll Pages until it serves exactly what we pushed."""
    want = hashlib.sha256(local_bytes).hexdigest()
    deadline = time.time() + budget
    while time.time() < deadline:
        try:
            req = urllib.request.Request(LIVE, headers={"User-Agent": "memwatch-cron/1.0",
                                                        "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if hashlib.sha256(r.read()).hexdigest() == want:
                    return True
        except Exception:
            pass
        time.sleep(10)
    return False


def push_with_retry(waits=(0, 15, 45)):
    """Retry network-shaped failures AND timeouts; an auth rejection fails at once."""
    last = (-1, "", "")
    for wait in waits:
        if wait:
            time.sleep(wait)
        last = git("push", "origin", BRANCH, timeout=240)
        if last[0] == 0:
            return last
        if last[0] == -1:                      # tree-killed timeout: transient by definition
            continue
        if not TRANSIENT.search((last[2] or "") + (last[1] or "")):
            break            # auth or policy failure: fail fast, do not retry
    return last


def ahead_count():
    """Commits built but never published — the stuck state a failed push leaves behind."""
    rc, out, _ = git("rev-list", "--count", "origin/%s..HEAD" % BRANCH)
    try:
        return int((out or "0").strip()) if rc == 0 else 0
    except ValueError:
        return 0


# ---------------------------------------------------------------- 1. preflight
rc, dirty, _ = git("status", "--porcelain", "--", *SOURCES)
if rc != 0:
    die("memwatch: git status failed — cannot verify the source tree: " + tail(dirty))
if dirty.strip():
    die("memwatch: source tree is dirty — refusing to build from a modified tree:\n" + dirty.strip())

backup = os.path.join(DATA, "spot_series.csv.bak")
shutil.copyfile(os.path.join(DATA, "spot_series.csv"), backup)

# ---------------------------------------------------------------- 2. collect + bake
rc, out, err = run([PY, os.path.join(DATA, "refresh.py")], timeout=600)
warn = ""
if rc != 0:
    shutil.copyfile(backup, os.path.join(DATA, "spot_series.csv"))
    die("memwatch: refresh FAILED (rc=%s) — site left untouched.\n%s" % (rc, tail(out + "\n" + err)))

rows = sum(1 for line in open(os.path.join(DATA, "spot_series.csv"), encoding="utf-8")
           if line.strip()) - 1
if rows < MIN_SPOT_ROWS:
    # Upstream degraded: keep the last good spot history, rebuild the rest anyway.
    shutil.copyfile(backup, os.path.join(DATA, "spot_series.csv"))
    run([PY, os.path.join(DATA, "build_dataset.py")], timeout=180)
    run([PY, os.path.join(DATA, "build.py")], timeout=180)
    warn = " [warn] spot re-parse degraded (%d rows) — kept last good NAND/DRAM spot history" % rows
os.remove(backup)

# ---------------------------------------------------------------- 3. gate the artifact
index_path = os.path.join(REPO, "index.html")
html = open(index_path, encoding="utf-8").read()
missing = [m for m in ("<title>Memwatch", "const DATA =", '"ddr5_retail"', '"nand_spot"',
                       "listing-mix") if m not in html]
if len(html) < 60000 or missing:
    die("memwatch: GATE FAILED (%d bytes, missing %s) — not deploying.\n%s"
        % (len(html), missing or "-", tail(out)))

# interactive-chart gate: hovering must repaint the frame, not stack crosshairs
rc, hv, hverr = run([PY, os.path.join(REPO, "scripts", "verify_hover.py")], timeout=300)
if rc != 0:
    die("memwatch: HOVER GATE FAILED — not deploying.\n%s" % tail(hv + "\n" + hverr))
# say so when the gate could not run, so a skipped check is never mistaken for a passed one
hover_note = (" hover-gate skipped (no headless browser in this context)" if "[skip]" in hv
              else " hover-gate ok")

ds = json.load(open(os.path.join(DATA, "dataset.json"), encoding="utf-8"))
st = ds["stats"]
s5, sd, sn = st["ddr5_retail"], st["dram_spot"], st["nand_spot"]
as_of = ds["as_of"]

# ---------------------------------------------------------------- 4. material change?
unchanged = (not FORCE) and head_signature() == signature(ds)
if unchanged:
    git("restore", "--worktree", "--", *(GENERATED + RAW))
    queued = ahead_count()
    if queued:
        # A previous run built and committed but its push failed. The data is unchanged
        # since then, so publish the backlog rather than skipping forever.
        rc, out, err = push_with_retry()
        rc2, sha2, _ = git("rev-parse", "--short", "HEAD")
        if rc != 0:
            die("memwatch %s — no new data, but %d queued commit(s) still unpushed: %s\n%s"
                % (as_of, queued, sha2.strip(), tail(out + "\n" + err)))
        live = live_matches(open(index_path, "rb").read())
        log("memwatch %s — no new upstream data; published %d queued commit(s) %s — %s%s" % (
            as_of, queued, sha2.strip(), "live verified" if live else "pushed (Pages building)", warn))
        sys.exit(0)
    log("memwatch %s — no new upstream data (DDR5 $%.2f/GB, NAND $%.2f). Nothing to publish." % (
        as_of, s5["last"], sn["last"]) + warn)
    sys.exit(0)

# ---------------------------------------------------------------- 5. commit + push
git("add", "--", *(GENERATED + RAW))
msg = ("daily: %s — DDR5 $%.2f/GB (%+.1f%% off peak), DDR4 chip $%.2f, NAND 512Gb $%.2f (%+.1f%% off peak)"
       % (as_of, s5["last"], s5["off_peak_pct"], sd["last"], sn["last"], sn["off_peak_pct"]))
rc, out, err = git("-c", "user.name=nwfella", "-c", "user.email=nwfella@users.noreply.github.com",
                   "commit", "-q", "-m", msg)
if rc != 0:
    die("memwatch: commit failed (rc=%s)\n%s" % (rc, tail(out + "\n" + err)))

rc, sha, _ = git("rev-parse", "--short", "HEAD")
sha = sha.strip()

if DRY:
    git("reset", "--soft", "HEAD~1")
    git("restore", "--worktree", "--", *GENERATED)
    log("memwatch %s — DRY RUN: would publish %s%s" % (as_of, sha, warn))
    sys.exit(0)

rc, out, err = push_with_retry()
if rc != 0:
    die("memwatch %s — PUSH FAILED, site is stale (committed %s locally).\n%s"
        % (as_of, sha, tail(out + "\n" + err)))

# ---------------------------------------------------------------- 6. report
live = live_matches(open(index_path, "rb").read())
log("memwatch %s — DDR5 $%.2f/GB (%+.1f%% 30d), DDR4 chip $%.2f%s, NAND 512Gb $%.2f (%+.1f%% off peak). "
    "Published %s — %s%s" % (
        as_of, s5["last"], s5["chg_30d"] or 0, sd["last"],
        " (record)" if sd["off_peak_pct"] >= -0.05 else "",
        sn["last"], sn["off_peak_pct"], sha,
        "live verified" if live else "pushed (Pages still building)", warn + hover_note))
