# Memwatch — DRAM, NAND & SSD price history

Live: **https://nwfella.github.io/memory-price-index/**

A single-file dashboard tracking the 2025–2026 memory supercycle from four angles at once, with every
point traceable to a dated public source. No build step, no dependencies, no runtime fetches — the data
is baked into the page.

![status](https://img.shields.io/badge/data%20through-2026--11--22-f5b845)
![license](https://img.shields.io/badge/license-MIT-blue)

## What it tracks

| Series | Unit | Cadence | Source |
|---|---|---|---|
| DDR5 desktop kits (retail) | $/GB | daily | [RamRadar RAM Price Index](https://ramradar.app/ram-price-index) |
| DDR4 desktop kits (retail) | $/GB | daily | RamRadar |
| DDR4 8Gb chip (spot) | $/chip | weekly | [TrendForce memory spot](https://www.trendforce.com/price/dram/dram_spot) |
| 512Gb TLC NAND wafer (spot) | $/wafer | weekly | [TrendForce wafer spot](https://www.trendforce.com/price/flash/wafer_spot) |
| Benchmark spot quotes | $/part | daily | the same two TrendForce boards, re-read at build |
| Client SSD OEM contract | $/drive | quarterly | TrendForce PC-client OEM SSD contract price |

## The read (22 Nov 2026)

**Both layers have turned. Retail is last.**

- **NAND has broken, not just softened.** 512Gb TLC wafers peaked at **$23.00** on 18 Mar 2026 and quote
  **$14.24** — **−38.1% off peak**, −24.4% in 30 days. Contract now agrees: TrendForce cut 4Q26 NAND contract
  growth to **+8–13% QoQ** on 19 Nov (from +15–20% on 30 Sep) and guides **0 to −5% in 1Q27**, with every
  product category in a down-cycle from 2Q27 and 2027 bit supply up 25–30%.
- **DRAM has followed at the spot layer.** The DDR4 8Gb benchmark peaked at **$47.04** on 27 Oct and sits at
  **$44.25** — **−5.9% off peak**, −4.5% in 30 days — and the daily board keeps printing small declines
  (43.75, −0.39% session, as of the 20 Nov read). Contract has not followed: PC DRAM is still guided
  **+13–18% QoQ** for 4Q26, and suppliers plan to cut PC DRAM *allocation* in 2027 rather than cut price.
- **Retail is barely cracking.** DDR5 kits are **−1.1%** off their 23 Oct record ($19.93/GB), DDR4 kits
  **−4.4%** off 5 Nov ($8.40/GB). Client SSD contract growth decelerated to **under +5% QoQ** for 4Q26 — the
  first near-flat quarter for a drive buyer in a year — against +285–303% YoY in 3Q26.
- **Demand is the tell.** Notebook shipments fell **−15.8% QoQ in 3Q26** with another decline guided for 4Q26;
  OEMs are revising 1Q27 procurement down and shifting toward lower-spec, private-label builds.

The headwinds are all on the consumer side. AI/HBM allocation still absorbs the wafers that would otherwise
set DDR5 and client-SSD prices — which is why contract prices rise while spot and retail roll over.

## Why it looks the way it does

- **Index mode rebases every series to 100 at the window start.** A chip sold by the wafer and a kit sold by
  the gigabyte are not comparable in dollars; they are comparable in multiples.
- **The drawdown chart is the honest answer to "is it coming down".** Zero means today is the record.
- **The prose is computed, not written.** The verdict, lede and verdict cards are derived from the stats at
  render time, so a headline cannot outlive the data it describes (the previous hand-written lede still called
  DDR4 spot a "record" three weeks after it had rolled over).
- **Nothing is interpolated.** Missing weeks stay missing; lines connect observations that exist.
- **Discontinuities are annotated, not smoothed.** The vertical marker in May 2026 is a listing-mix change in
  the upstream retail index (the cheapest tracked DDR5 kit jumped $3.17 → $6.77/GB as cheap listings aged
  out), not an overnight price cut. Days with fewer than 10 tracked kits are excluded.
- **No invented numbers.** The SSD ladder shows a prior-quarter delta only where a prior quarter actually
  exists in the dataset; the other two tiers show actuals and say so. Superseded guidance prints stay in the
  table with their date instead of being quietly overwritten by the newest one.


## Automation

A Hermes cron job (`Memwatch daily refresh`, 07:40 local) runs `scripts/daily_refresh.py` every day with
no LLM in the loop:

1. re-download the retail index, re-read both live spot boards, re-discover and re-parse the weekly spot posts
2. **guard (spot):** if the TrendForce re-parse degrades below 20 priced posts, `spot_series.csv` is left exactly
   as it was — one bad upstream day cannot wipe 12 months of history off the chart
3. **guard (build):** a series with no priced points is a warning, not a crash — the build keeps going
4. **gate:** the rebuilt page must pass size + marker checks, and all four series must carry a usable history,
   or nothing is deployed
5. **hover gate:** `scripts/verify_hover.py` sweeps 61 synthetic mousemoves across the chart in headless Chrome
   and asserts exactly one crosshair column is painted (idle 0, after sweep 1, after leave 0). The smear bug this
   catches drew 59 stacked lines and never cleared them
6. **publish:** commit `index.html` + the data files and push (non-interactive git, network-only retries),
   then poll Pages until the live bytes match the pushed bytes
7. **quiet:** if the material data is unchanged, the run publishes nothing and restores its worktree — but a
   stranded backlog (a commit whose push failed) is always counted and re-pushed

Stdout is the daily report — one line, e.g.
`memwatch 2026-11-22 — DDR5 $19.93/GB (-1.1% 30d), DDR4 chip $44.25, NAND 512Gb $14.24 (-38.1% off peak). Published 2da6cad — live verified`

### When TrendForce is unreachable

It happens — this network intermittently fails TLS (a stale CA bundle rejects the DigiCert chain) or DNS. Both
spots scripts now use a certifi CA bundle and retry, and the spot steps are **soft**: retail data still builds
and publishes, the spot history is preserved, and the board rows keep showing their own "Last Update" date rather
than pretending to be current. Retail (RamRadar) is the only hard requirement, because it is the core series.

## Rebuild

```bash
python data/refresh.py
```

1. re-downloads the RamRadar daily CSV
2. re-reads the live TrendForce spot boards into `data/spot_board.json`
3. re-fetches and re-parses every TrendForce weekly spot post listed in `data/spot_urls.txt`
4. rebuilds `data/dataset.json` (stats, drawdown, marks, snapshot, guidance)
5. rebuilds `index.html` with the data inlined

To add a week, append the post URL to `data/spot_urls.txt`
(`trendforce.com/news/YYYY/MM/DD/insights-memory-spot-price-update-*`). TrendForce revises old posts, so the
whole list is re-parsed each run.

```
data/
  ramradar.csv          raw daily retail index (as downloaded)
  spot_urls.txt         the TrendForce posts feeding the spot series (auto-extended on refresh)
  spot_series.csv       parsed weekly quotes (one row per post, with URL)
  spot_board.json       last good read of both live spot boards (name/value/session change/as-of)
  fetch_spot_quotes.py  parser for the weekly posts
  fetch_spot_board.py   parser for the live spot boards
  build_dataset.py      joins everything, computes stats + marks + snapshot + guidance
  build.py              template + data -> index.html
  refresh.py            the five steps above, in order
template.html           markup/CSS/JS with a /*__DATA__*/ placeholder
index.html              the deployed artifact (generated — edit the template)
```

## Limits

Retail figures are **asking prices**, not transactions: RamRadar records the lowest live listing per kit from
eBay/Newegg (B&H until Sep 2026), so an open-box item can enter the pool and coverage is eBay-weighted. Spot
is a thin, broker-driven market for loose chips; contract is what OEMs pay quarterly. Spot moves first and
overshoots — a falling wafer quote leads SSD pricing by weeks to months, it does not mean a specific drive got
cheaper today. Not investment advice.

## License

MIT © nwfella. See [LICENSE](LICENSE).
