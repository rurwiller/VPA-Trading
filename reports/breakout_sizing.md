# Breakout sizing: fixed $75k vs volatility-based

Fixed: $75,000 of stock every trade (live until Nov 2026).
Vol-sized: notional = budget / (the stock's 20-day realized daily volatility, known at the prior close), so a typical
day's move is worth the same dollars on every symbol and in every market; capped at $150,000.
The budget is set so the average notional on TSLA + QQQ over the discovery period is about $75,000 (same capital use).
Daily breakout returns from results/strategy_history.pkl (live rules, after cost). Discovery before 2026-05-21, holdout
after, shown once.

Budget = $1,688 of one day's typical move per trade (so a stock moving 2% a day gets $84,401, one moving 4% gets $42,201).

Per symbol and portfolio, in dollars per day: average | Sharpe | worst day | worst drawdown.

| Book | Sizing | Discovery | Holdout |
|---|---|---|---|
| TSLA | fixed $75k | +50 | 0.99 | -3,468 | -17,518 | +62 | 1.54 | -1,473 | -3,357 |
| TSLA | vol-sized | +35 | 1.04 | -2,014 | -12,226 | +47 | 1.47 | -1,611 | -3,399 |
| TSLA | vol-sized notional | median $49,309, range $30,089 to $78,847 | |
| QQQ | fixed $75k | +28 | 1.23 | -1,620 | -7,762 | +23 | 1.08 | -824 | -2,942 |
| QQQ | vol-sized | +47 | 1.31 | -2,009 | -14,618 | +49 | 1.32 | -1,498 | -3,972 |
| QQQ | vol-sized notional | median $142,504, range $70,471 to $150,000 | |
| NVDA | fixed $75k | +19 | 0.41 | -3,847 | -24,523 | +44 | 1.25 | -1,493 | -4,093 |
| NVDA | vol-sized | +11 | 0.30 | -3,185 | -25,226 | +44 | 1.20 | -1,928 | -4,536 |
| NVDA | vol-sized notional | median $59,399, range $32,051 to $100,465 | |
| TSLA + QQQ | fixed $75k | +78 | 1.29 | -3,855 | -16,306 | +85 | 1.72 | -1,908 | -3,388 |
| TSLA + QQQ | vol-sized | +81 | 1.51 | -2,350 | -13,169 | +96 | 1.77 | -1,676 | -3,458 |
