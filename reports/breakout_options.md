# The trend-day breakout as options

The trend-day breakout traded as options instead of stock (step 4 of the overhaul), TSLA and QQQ, Feb 2024 on
(Alpaca's historical option bars start then).

1. Every breakout trade is rebuilt minute by minute with the live rules: checks every 30 minutes from 10:00, entry
   above / below the noise band, thirds sold at +1% and +2% with the stop moved to breakeven after the first, a
   2.5% protective stop, the 15m-oscillator trim of half at 80/20, exit when price is back inside the band (or VWAP),
   out by the close. (Not modelled: the live exit on an opposite high-volume candle.)
2. Each trade is priced as three option choices, bought at the entry minute and sold piece by piece at the stock's
   exit minutes (same fractions): calls for longs, puts for shorts.
     nearest ATM     the nearest expiry (0DTE on most days for QQQ), strike closest to the entry price
     ~1 week ITM     the first expiry at least 5 days out, one strike in the money
     ~2 weeks ATM    the first expiry at least 10 days out, at the money
   Price = the option's last trade at or before the minute (at most 15 minutes old; otherwise the trade is skipped).
3. Costs: Alpaca's history has trades, not quotes, so a round-trip spread is assumed (QQQ 2% nearest / 1% later
   expiries; TSLA 3% / 1.5%, of the option's price), and results are also shown before it.
Comparison at equal risk: the stock is sized by volatility ($1,700 of a typical day's move), the option spends
$1,700 of premium (the most it can lose). Holdout = 2026-05-21 on.

1344 trades, 2024-02-01 to 2026-11-03. Median holding time 60 minutes.


## All trades

| Instrument | Trades priced | Avg per trade | Before spread | Won | $ per trade at equal risk | Total $ |
|---|--:|--:|--:|--:|--:|--:|
| Stock, vol-sized | 1344 | +0.02% of notional | | 48% | +19 | +25,138 |
| Nearest expiry, ATM | 1324 | -1.2% of premium | +1.3% | 35% | -21 | -27,277 |
| (stock on the same 1324 trades) | | | | | +14 | +18,834 |
| ~1 week, 1 strike ITM | 1234 | -1.5% of premium | -0.2% | 40% | -26 | -31,972 |
| (stock on the same 1234 trades) | | | | | -20 | -24,451 |
| ~2 weeks, ATM | 1004 | -1.6% of premium | -0.3% | 37% | -27 | -27,423 |
| (stock on the same 1004 trades) | | | | | -27 | -27,321 |

## Before the holdout

| Instrument | Trades priced | Avg per trade | Before spread | Won | $ per trade at equal risk | Total $ |
|---|--:|--:|--:|--:|--:|--:|
| Stock, vol-sized | 1143 | +0.01% of notional | | 48% | +12 | +14,037 |
| Nearest expiry, ATM | 1123 | -3.3% of premium | -0.8% | 35% | -57 | -63,624 |
| (stock on the same 1123 trades) | | | | | +7 | +7,734 |
| ~1 week, 1 strike ITM | 1049 | -1.7% of premium | -0.4% | 40% | -29 | -29,960 |
| (stock on the same 1049 trades) | | | | | -24 | -25,331 |
| ~2 weeks, ATM | 883 | -1.7% of premium | -0.3% | 37% | -29 | -25,192 |
| (stock on the same 883 trades) | | | | | -27 | -23,752 |

## Holdout (2026-05-21 on)

| Instrument | Trades priced | Avg per trade | Before spread | Won | $ per trade at equal risk | Total $ |
|---|--:|--:|--:|--:|--:|--:|
| Stock, vol-sized | 201 | +0.07% of notional | | 46% | +55 | +11,100 |
| Nearest expiry, ATM | 201 | +10.6% of premium | +13.2% | 34% | +181 | +36,347 |
| (stock on the same 201 trades) | | | | | +55 | +11,100 |
| ~1 week, 1 strike ITM | 185 | -0.6% of premium | +0.6% | 42% | -11 | -2,012 |
| (stock on the same 185 trades) | | | | | +5 | +880 |
| ~2 weeks, ATM | 121 | -1.1% of premium | +0.3% | 36% | -18 | -2,231 |
| (stock on the same 121 trades) | | | | | -30 | -3,570 |

### TSLA

| Instrument | Trades | Avg per trade | Won | $ per trade at equal risk |
|---|--:|--:|--:|--:|
| Stock | 746 | +0.01% | 50% | +11 |
| nearest | 735 | -2.1% | 39% | -35 |
| week | 717 | -1.1% | 41% | -19 |
| two_weeks | 670 | -1.6% | 39% | -27 |

### QQQ

| Instrument | Trades | Avg per trade | Won | $ per trade at equal risk |
|---|--:|--:|--:|--:|
| Stock | 598 | +0.02% | 45% | +28 |
| nearest | 589 | -0.1% | 31% | -3 |
| week | 517 | -2.1% | 38% | -35 |
| two_weeks | 334 | -1.7% | 34% | -29 |
