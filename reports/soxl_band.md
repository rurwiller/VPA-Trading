# SOXL fixed-dollar band strategy (from the post), rebuilt and stress-tested

Rules as described in the post:
  - Start: $5,000 of SOXL (bought at the first open) and $5,000 cash. Target stays $5,000 for good.
  - After each close, value the SOXL shares at the close:
      at or below 90% of target  -> buy back up to the target at the next open (only with cash on hand)
      at or above 110% of target -> trim back to the target at the next open
      ...but in a strong trend the trim trigger is 150% ($7,500). Strong trend = SOXX closes above its 20-day average
         and the 20-day average is above the 100-day average (today counted in both).
  - Orders are sized at the next open from the open price (a gap can shrink or cancel them). Fractional shares.
    Cost 0.10% of each trade after the first. Cash earns nothing. No deposits, no borrowing.
Data: Alpaca daily bars, split-adjusted only (no dividends; SOXL pays almost none), 2016 to Nov 2026.

Tested: the base rule from every month-start 2017-2025 (not just one lucky start), the band settings moved around,
no trend rule, and benchmarks (half SOXL / half cash held, all SOXL, all SOXX, SPY, QQQ, QQQ 200-day sleeve).

Data 2016-05-25 to 2026-11-25 (after the 100-day warm-up).
Cells: final value of $10,000 | yearly growth | Sharpe | worst drop from a high.


## From the first possible day (2016-05-25 to 2026-11-25)

| Approach | Result |
|---|---|
| Band strategy (post's rules) | $52,794 | +17.2% | 0.94 | -25.5% |
| Same start, held: $5k SOXL + $5k cash | $90,296 | +23.4% | 0.70 | -89.2% |
| All $10k in SOXL, held | $170,591 | +31.1% | 0.79 | -90.5% |
| All $10k in SOXX, held | $123,176 | +27.1% | 0.85 | -46.2% |
| All $10k in SPY, held | $34,345 | +12.5% | 0.75 | -34.2% |
| All $10k in QQQ, held | $58,413 | +18.3% | 0.86 | -35.6% |
| QQQ 200-day sleeve (our live rule, full $10k) | $44,997 | +15.4% | 0.95 | -21.9% |

Band strategy: 284 trades; 0 buys cut short for lack of cash; lowest cash $4,303.

## From January 2022 (the post's bad start) (2022-01-03 to 2026-11-25)

| Approach | Result |
|---|---|
| Band strategy (post's rules) | $22,194 | +17.2% | 0.58 | -79.8% |
| Same start, held: $5k SOXL + $5k cash | $7,221 | -6.5% | 0.12 | -72.4% |
| All $10k in SOXL, held | $4,441 | -15.3% | 0.48 | -90.4% |
| All $10k in SOXX, held | $20,823 | +16.2% | 0.57 | -46.0% |
| All $10k in SPY, held | $15,046 | +8.7% | 0.56 | -25.4% |
| All $10k in QQQ, held | $15,886 | +10.0% | 0.52 | -35.2% |
| QQQ 200-day sleeve (our live rule, full $10k) | $16,170 | +10.1% | 0.68 | -20.9% |

Band strategy: 148 trades; 162 buys cut short for lack of cash; lowest cash $0.

## 2026 only (the post's main example) (2026-01-02 to 2026-11-25)

| Approach | Result |
|---|---|
| Band strategy (post's rules) | $15,150 | +54.9% | 1.12 | -39.2% |
| Same start, held: $5k SOXL + $5k cash | $8,389 | -17.8% | 0.39 | -77.6% |
| All $10k in SOXL, held | $6,778 | -35.2% | 0.58 | -89.7% |
| All $10k in SOXX, held | $12,240 | +25.3% | 0.68 | -43.5% |
| All $10k in SPY, held | $10,521 | +5.9% | 0.44 | -11.5% |
| All $10k in QQQ, held | $10,407 | +4.6% | 0.31 | -19.9% |
| QQQ 200-day sleeve (our live rule, full $10k) | $9,962 | -0.2% | 0.09 | -16.1% |

Band strategy: 44 trades; 0 buys cut short for lack of cash; lowest cash $5,000.

## Five years, as in the post (2021-11-24 to 2026-11-25)

| Approach | Result |
|---|---|
| Band strategy (post's rules) | $22,971 | +17.5% | 0.57 | -78.8% |
| Same start, held: $5k SOXL + $5k cash | $7,394 | -5.9% | 0.14 | -73.4% |
| All $10k in SOXL, held | $4,788 | -13.7% | 0.49 | -90.5% |
| All $10k in SOXX, held | $21,585 | +16.7% | 0.58 | -46.2% |
| All $10k in SPY, held | $15,311 | +8.9% | 0.57 | -25.4% |
| All $10k in QQQ, held | $16,002 | +9.9% | 0.52 | -35.5% |
| QQQ 200-day sleeve (our live rule, full $10k) | $16,185 | +10.1% | 0.67 | -21.2% |

Band strategy: 149 trades; 114 buys cut short for lack of cash; lowest cash $0.

## Every start month, 2016-2025, held to Nov 24 2026

115 start months. Band strategy vs holding $5k SOXL + $5k cash from the same day, and vs SPY.

| | Band strategy | Held half SOXL | SPY |
|---|--:|--:|--:|
| Median final value of $10k | $31,229 | $15,038 | $19,115 |
| Worst final value | $14,604 | $7,221 | $10,519 |
| Starts that ended below $10,000 | 0 | 26 | 0 |
| Median worst drawdown | -44% | -85% | -25% |
| Worst drawdown of any start | -80% | -89% | -34% |
| Band beat held-half-SOXL | 94% of starts | | |
| Band beat SPY | 100% of starts | | |

Worst starts for the band strategy: Nov 2025 -> $14,604 (drawdown -40%), Dec 2025 -> $15,450 (drawdown -39%), Oct 2025 -> $16,656 (drawdown -37%)

## How much the settings matter (from the first possible day)

| Buy band | Trim band | Strong-trend trigger | Trend rule | Result | Trades |
|--:|--:|--:|---|---|--:|
| 10% | 10% | 150% of target | on | $52,794 | +17.2% | 0.94 | -25.5% | 284 |
| 10% | 10% | 150% of target | off | $50,754 | +16.8% | 0.94 | -25.3% | 441 |
| 5% | 5% | 150% of target | on | $55,313 | +17.7% | 0.98 | -24.6% | 582 |
| 15% | 15% | 150% of target | on | $52,094 | +17.0% | 0.92 | -25.7% | 173 |
| 20% | 20% | 150% of target | on | $52,537 | +17.1% | 0.94 | -26.1% | 119 |
| 10% | 10% | 130% of target | on | $53,368 | +17.3% | 0.97 | -25.4% | 313 |
| 10% | 10% | 200% of target | on | $52,072 | +17.0% | 0.90 | -26.1% | 274 |
| 10% | 10% | 300% of target | on | $53,422 | +17.3% | 0.91 | -26.1% | 272 |
| 20% | 10% | 150% of target | on | $50,714 | +16.7% | 0.92 | -26.9% | 171 |
| 10% | 20% | 150% of target | on | $54,761 | +17.6% | 0.97 | -25.1% | 201 |
