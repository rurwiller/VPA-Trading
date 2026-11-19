# The gold opening-range breakdown on gold's relatives (5 years of 1m bars)

Same rule and scaling as commodity_orb_test.py: on gap-down days, short when a 30-minute block closes below the first
30 minutes' low; stop 0.97 x and target 0.73 x the 14-day average daily range; one trade a day; out by the close.
Costs are estimated (round-trip spread + 1 bp) and rough for the thin funds, so the before-cost column is shown too.

Each cell: trades | average bps per trade | t (mean / standard error; above about 2 is unlikely to be luck).


## The rule: short on gap-down days

| Fund | Market | Before costs | After costs | Before Nov 2024 | Since Nov 2024 | Win % |
|---|---|---|---|---|---|---|
| GLD | gold (reference) | 271 | +6.8 | +2.6 | 271 | +5.2 | +2.0 | 164 | +5.8 | +2.3 | 107 | +4.2 | +0.8 | 53 |
| GDX | gold miners | 251 | +3.1 | +0.4 | 251 | +0.6 | +0.1 | 154 | +2.3 | +0.3 | 97 | -2.0 | -0.2 | 52 |
| GDXJ | junior gold miners | 254 | +9.5 | +1.2 | 254 | +5.5 | +0.7 | 159 | +9.5 | +1.1 | 95 | -1.3 | -0.1 | 50 |
| NEM | Newmont | 232 | +0.3 | +0.0 | 232 | -2.2 | -0.3 | 140 | +4.7 | +0.5 | 92 | -12.7 | -1.0 | 47 |
| AEM | Agnico Eagle | 245 | +3.6 | +0.5 | 245 | +1.1 | +0.1 | 150 | +2.7 | +0.3 | 95 | -1.4 | -0.1 | 50 |
| SIL | silver miners | 246 | +3.3 | +0.4 | 246 | -4.7 | -0.6 | 154 | +5.4 | +0.6 | 92 | -21.6 | -1.5 | 48 |
| FXF | Swiss franc | 94 | +2.7 | +1.3 | 94 | -7.3 | -3.5 | 4 | -13.2 | -1.4 | 90 | -7.0 | -3.3 | 33 |
| FXY | Japanese yen | 350 | +2.3 | +2.4 | 350 | -2.7 | -2.7 | 179 | -2.2 | -1.4 | 171 | -3.2 | -2.9 | 41 |
| UUP | US dollar | 305 | +0.0 | +0.0 | 305 | -5.0 | -4.4 | 177 | -4.0 | -2.5 | 128 | -6.4 | -4.0 | 38 |
| TLT | 20y+ Treasuries | 382 | +0.8 | +0.4 | 382 | -1.2 | -0.6 | 220 | -1.3 | -0.4 | 162 | -1.1 | -0.4 | 48 |
| IEF | 7-10y Treasuries | 371 | +0.6 | +0.6 | 371 | -1.6 | -1.5 | 213 | -1.2 | -0.8 | 158 | -2.1 | -1.5 | 44 |

## Contrast: the same short on days that did NOT gap down

| Fund | Market | Before costs | After costs | Before Nov 2024 | Since Nov 2024 | Win % |
|---|---|---|---|---|---|---|
| GLD | gold (reference) | 343 | +2.0 | +0.8 | 343 | +0.4 | +0.2 | 201 | -2.5 | -0.9 | 142 | +4.6 | +1.0 | 49 |
| GDX | gold miners | 313 | -3.6 | -0.6 | 313 | -6.1 | -1.0 | 180 | +2.7 | +0.3 | 133 | -18.0 | -1.7 | 49 |
| GDXJ | junior gold miners | 316 | -4.2 | -0.6 | 316 | -8.2 | -1.1 | 179 | -1.5 | -0.2 | 137 | -16.9 | -1.5 | 46 |
| NEM | Newmont | 285 | +2.0 | +0.3 | 285 | -0.5 | -0.1 | 176 | +5.7 | +0.8 | 109 | -10.5 | -0.9 | 49 |
| AEM | Agnico Eagle | 300 | -6.0 | -0.9 | 300 | -8.5 | -1.2 | 175 | -1.3 | -0.1 | 125 | -18.5 | -1.7 | 50 |
| SIL | silver miners | 317 | -6.8 | -0.9 | 317 | -14.8 | -2.0 | 177 | -9.4 | -1.0 | 140 | -21.6 | -1.9 | 44 |
| FXF | Swiss franc | 80 | -0.7 | -0.3 | 80 | -10.7 | -4.4 | 3 | -5.3 | -0.7 | 77 | -10.9 | -4.3 | 34 |
| FXY | Japanese yen | 305 | +0.7 | +0.6 | 305 | -4.3 | -3.5 | 139 | -7.2 | -3.6 | 166 | -1.9 | -1.3 | 47 |
| UUP | US dollar | 348 | -0.2 | -0.2 | 348 | -5.2 | -5.4 | 204 | -4.6 | -3.4 | 144 | -6.1 | -4.5 | 36 |
| TLT | 20y+ Treasuries | 328 | -2.7 | -1.1 | 328 | -4.7 | -1.8 | 193 | -8.2 | -2.1 | 135 | +0.2 | +0.1 | 45 |
| IEF | 7-10y Treasuries | 357 | -1.3 | -1.2 | 357 | -3.5 | -3.1 | 203 | -4.8 | -2.7 | 154 | -1.9 | -1.4 | 42 |
