# Micro Gold opening-range breakdown (tested on GLD, 5 years of 1m bars)

Rules as posted:
  - trade only on days gold opens below the prior close
  - mark the low of the first 30 minutes
  - short when a 30-minute block closes below it (entry at that block's close)
  - stop 20 points, target 15 points, else out at the 4 PM close; one trade a day
GLD stands in for gold futures: 1 futures point = 1/10.86 of a GLD dollar (GLD holds ~0.092 oz). Session = 9:30-16:00 ET
(the post's "4 PM close"), 30-minute blocks from 9:30. Same 1m bar touching stop and target = stop. Cost 0.4 futures points
per round trip (about a tick each way plus micro fees). 1 point = $10 on one Micro Gold contract.
Variants: the same stop/target as a share of price (20 and 15 points were sized for ~$1,800 gold in 2021), the mirrored
long on gap-up days, and the short on days that did NOT gap down (does the gap filter matter?).

Data 2021-11-08 to 2026-11-05. Points are gold-futures points after costs; $ is for one Micro Gold contract ($10 a point). t = mean / standard error.


## As posted: short, gap-down days, 20 / 15 points

| Period | Trades | Won | Avg points | $ total (1 MGC) | t |
|---|--:|--:|--:|--:|--:|
| All | 274 | 55% | +1.25 | +3,414 | +2.1 |
| Before Nov 2024 | 169 | 52% | +0.85 | +1,433 | +1.6 |
| Since Nov 2024 | 105 | 59% | +1.89 | +1,982 | +1.5 |

By year (trades, avg points): 2021 9 / -0.5, 2022 67 / -0.0, 2023 51 / +1.9, 2024 53 / +1.4, 2025 41 / +2.6, 2026 53 / +1.3
How trades ended: 4 PM close 72%, target 21%, stop 7%. Gold price at entry 1,649-5,131; 20 points was 1.06% of price at the start and 0.51% at the end.

## Short, gap-down days, stop/target scaled to the gold price

| Period | Trades | Won | Avg points | $ total (1 MGC) | t |
|---|--:|--:|--:|--:|--:|
| All | 274 | 53% | +1.36 | +3,724 | +1.6 |
| Before Nov 2024 | 169 | 52% | +0.83 | +1,399 | +1.6 |
| Since Nov 2024 | 105 | 53% | +2.21 | +2,325 | +1.1 |

By year (trades, avg points): 2021 9 / -0.5, 2022 67 / +0.2, 2023 51 / +1.9, 2024 53 / +1.2, 2025 41 / +1.4, 2026 53 / +2.8
How trades ended: 4 PM close 90%, target 9%, stop 1%. Gold price at entry 1,649-5,131; 20 points was 1.06% of price at the start and 0.51% at the end.

## Short on days that did NOT gap down (gap filter off)

| Period | Trades | Won | Avg points | $ total (1 MGC) | t |
|---|--:|--:|--:|--:|--:|
| All | 347 | 48% | -0.56 | -1,950 | -1.0 |
| Before Nov 2024 | 205 | 45% | -0.47 | -970 | -0.8 |
| Since Nov 2024 | 142 | 51% | -0.69 | -980 | -0.6 |

By year (trades, avg points): 2021 9 / +0.4, 2022 64 / +0.8, 2023 68 / +0.1, 2024 75 / -1.9, 2025 68 / -0.9, 2026 63 / -0.8
How trades ended: 4 PM close 68%, target 20%, stop 12%. Gold price at entry 1,647-5,279; 20 points was 1.08% of price at the start and 0.49% at the end.

## Mirror: long on gap-up days above the first-30-min high

| Period | Trades | Won | Avg points | $ total (1 MGC) | t |
|---|--:|--:|--:|--:|--:|
| All | 386 | 54% | +0.53 | +2,060 | +1.0 |
| Before Nov 2024 | 221 | 55% | +1.16 | +2,559 | +2.1 |
| Since Nov 2024 | 165 | 54% | -0.30 | -500 | -0.3 |

By year (trades, avg points): 2021 8 / +2.5, 2022 76 / -0.9, 2023 63 / +2.6, 2024 86 / +1.8, 2025 87 / +3.0, 2026 66 / -4.9
How trades ended: 4 PM close 67%, target 21%, stop 12%. Gold price at entry 1,661-5,291; 20 points was 1.08% of price at the start and 0.49% at the end.

## Short, gap-down days, 15 / 15 points

| Period | Trades | Won | Avg points | $ total (1 MGC) | t |
|---|--:|--:|--:|--:|--:|
| All | 274 | 52% | +0.51 | +1,408 | +0.9 |
| Before Nov 2024 | 169 | 52% | +0.82 | +1,392 | +1.5 |
| Since Nov 2024 | 105 | 51% | +0.01 | +15 | +0.0 |

By year (trades, avg points): 2021 9 / -0.5, 2022 67 / -0.0, 2023 51 / +1.8, 2024 53 / +1.4, 2025 41 / +1.4, 2026 53 / -1.5
How trades ended: 4 PM close 68%, target 18%, stop 14%. Gold price at entry 1,649-5,131; 20 points was 1.06% of price at the start and 0.51% at the end.

## Short, gap-down days, 20 / 30 points

| Period | Trades | Won | Avg points | $ total (1 MGC) | t |
|---|--:|--:|--:|--:|--:|
| All | 274 | 52% | +1.17 | +3,196 | +1.6 |
| Before Nov 2024 | 169 | 52% | +0.50 | +852 | +1.0 |
| Since Nov 2024 | 105 | 52% | +2.23 | +2,343 | +1.3 |

By year (trades, avg points): 2021 9 / -0.5, 2022 67 / -0.1, 2023 51 / +1.7, 2024 53 / +0.9, 2025 41 / +1.7, 2026 53 / +2.4
How trades ended: 4 PM close 84%, stop 8%, target 7%. Gold price at entry 1,649-5,131; 20 points was 1.06% of price at the start and 0.51% at the end.
