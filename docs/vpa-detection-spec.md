# VPA Detection Spec — Anna Coulling's Volume Price Analysis

**Purpose:** a complete, implementation-ready reference for detecting the signals, sequences and structures described in Anna Coulling's *A Complete Guide to Volume Price Analysis*, applied to **stocks, OHLCV candle data only**.

**Audience:** a Claude Code session building pattern detectors. Read sections 0–2 before writing any code.

---

## 0. How to read this document

### Source tags
Every rule is tagged so you know how much to trust it.

| Tag | Meaning |
|---|---|
| **[Read]** | Confirmed directly from book pages we reviewed (chapters 1–6, 10–11). |
| **[Book]** | Coulling covers this. Detail is from general knowledge of the book and should be spot-checked against the text if precision matters. |
| **[Interp]** | Our numeric translation. Coulling deliberately gives **no numbers**; she judges volume and spread by eye, relative to recent bars. Every threshold here is a tunable default, not her rule. |

### Naming convention: Coulling, not Wyckoff/VSA
This spec uses **Coulling's definitions**. They are the reverse of traditional Wyckoff/VSA naming for climaxes. Coulling names the climax by **what the insiders are doing**; Wyckoff/VSA names it by **what the public is doing**.

| Location | Coulling (this spec) | Wyckoff / VSA name | Implication |
|---|---|---|---|
| Top of an uptrend, insiders selling into public buying | **Selling Climax** | Buying Climax | Bearish |
| Bottom of a downtrend, insiders buying from panicking public | **Buying Climax** | Selling Climax | Bullish |

Use Coulling names in all code identifiers and labels: `SELLING_CLIMAX` means a bearish top. Keep this mapping table in a code comment so nobody "fixes" it.

### Core philosophy to encode [Read]
- VPA is an **art, not a science**. Detectors produce *evidence with a confidence score*, never certainty.
- Every bar is checked for exactly one of two things: **validation** (volume agrees with price) or **anomaly** (volume disagrees with price). Nothing else matters. Anomalies are where the information is.
- Volume is **always relative**: to recent bars on the same chart and timeframe. There is no absolute "high volume."
- **Context beats shape.** The same candle means opposite things at the top of a trend, the bottom of a trend, or in the middle of a range.
- Single signals are warnings. **Repeated** signals in the same price area increase significance sharply.

---

## 1. Data model and derived metrics

### Input
```
Bar { t, open, high, low, close, volume }   // stocks; any timeframe
```

### Per-bar derived fields [Interp]
```
range      = high - low
body       = abs(close - open)
upperWick  = high - max(open, close)
lowerWick  = min(open, close) - low
dir        = close > open ? UP : close < open ? DOWN : FLAT
closeLoc   = range > 0 ? (close - low) / range : 0.5   // 0 = closed on low, 1 = closed on high
ATR14      = Wilder ATR, 14 bars
```

### Relative volume [Interp]
```
avgVol(i)  = SMA(volume, 20) over bars i-20 .. i-1     // exclude the current bar
relVol(i)  = volume(i) / avgVol(i)
```

**Intraday stocks: normalize for time of day.** US equity volume is U-shaped, heavy at the open and close and light midday. A raw 20-bar average will flag every opening bar as "high." For intraday timeframes, use:
```
relVolTOD(i) = volume(i) / median(volume of the same time slot over the prior 10–20 sessions)
```
Use `relVolTOD` wherever `relVol` appears below when the timeframe is under daily. Daily and slower bars can use plain `relVol`.

### Volume classes [Read for the four levels; Interp for cut-offs]
Coulling grades volume as low, average, high and ultra high.

| Class | relVol |
|---|---|
| `LOW` | < 0.7 |
| `AVERAGE` | 0.7 – 1.3 |
| `HIGH` | 1.3 – 2.0 |
| `ULTRA_HIGH` | ≥ 2.0 |

Also compute `volRising(i, n=3)` = volume strictly or mostly increasing over the last n bars (e.g. linear-regression slope > 0).

### Spread classes [Interp]
Coulling calls the candle body/range the "spread."
```
relRange = range / SMA(range, 20)   (or range / ATR14)
NARROW   : relRange < 0.7
AVERAGE  : 0.7 – 1.3
WIDE     : > 1.3
```

### Trend context [Interp]
Coulling identifies trend visually. A workable definition:
```
trendState(i, lookback = 15):
  slope   = linear-regression slope of close over lookback, divided by ATR14
  above   = fraction of closes above EMA21 over lookback
  UPTREND   if slope >  +0.08 and above >= 0.6  and pivots show higher highs/lows
  DOWNTREND if slope <  -0.08 and above <= 0.4  and pivots show lower highs/lows
  else RANGE
```
Also track `trendMaturity` = number of bars since the trend began. Climaxes need a **mature, extended** trend, not a fresh one.

### No look-ahead rule
A detection at bar `i` may only use data from bars `<= i`. Confirmation that arrives later (a test, a breakout, the move that followed) goes into a separate `confirmedAt` field with its own index. Never let future bars change whether bar `i` was flagged. This is the main criticism of every competing replay tool.

### Detection output schema
```
Detection {
  type          // e.g. SHOOTING_STAR, SELLING_CLIMAX, TEST_OF_SUPPLY
  bars          // [startIndex, endIndex] or single index
  bias          // BULLISH | BEARISH | NEUTRAL | WAIT
  volumeClass   // LOW | AVERAGE | HIGH | ULTRA_HIGH
  verdict       // VALIDATION | ANOMALY
  context       // UPTREND | DOWNTREND | RANGE, plus phase if known
  confidence    // 0–1
  repeatCount   // same signal in same price area recently (section 4)
  notes         // human-readable reason, for coaching text
  confirmedAt?  // index of later confirming bar, if any
}
```

---

## 2. Foundations to encode as logic

### 2.1 Wyckoff's three laws [Read]
Coulling builds on Wyckoff.
1. **Supply and demand.** Price rises when demand exceeds supply and falls when supply exceeds demand.
2. **Cause and effect.** The longer the "cause" (time spent in a congestion/accumulation/distribution range), the larger the "effect" (the trend that follows). Encode: breakout target or confidence scales with range duration.
3. **Effort and result.** Volume is effort; price movement is result. They should match. A mismatch is an anomaly.

### 2.2 Validation vs anomaly at the candle level [Read]
This is the single most important check. Run it on every bar.

| Spread | Volume | Verdict | Reading |
|---|---|---|---|
| WIDE | HIGH / ULTRA_HIGH | Validation | Genuine move; effort matches result |
| NARROW | LOW | Validation | Little interest, little movement; consistent |
| WIDE | LOW | **Anomaly** | Big move with no effort. Suspicious, possibly a trap or insiders moving price. Do not trust it. |
| NARROW | HIGH / ULTRA_HIGH | **Anomaly** | Big effort, no result. Something is absorbing the move. In an uptrend: selling into it (weakness). In a downtrend: buying into it (strength). |

### 2.3 Validation at the trend level [Read]
Coulling's second level: the **collective** candles must validate the trend.
- **Rising market must have rising volume.** Rising prices on **falling** volume is a classic sign of weakness. Coulling repeats this many times.
- **Falling market must also have rising volume.** Her gravity analogy: it still takes effort for a market to fall. A falling market on falling volume is suspect and may be running out of sellers.

Detection [Interp]:
```
over a trend leg (pivot to pivot, >= 5 bars):
  priceSlope = regression slope of close
  volSlope   = regression slope of volume
  UPTREND and volSlope < 0   -> TREND_ANOMALY_WEAK_RALLY   (bearish warning)
  DOWNTREND and volSlope < 0 -> TREND_ANOMALY_WEAK_DECLINE (selling drying up; bullish warning)
  slope signs agree          -> TREND_VALIDATED
```
Also compare successive **waves**: if each new push higher has lower average volume than the previous push, flag it.

### 2.4 Up in stairs, down in elevators [Read]
Markets climb slowly as confidence builds and fall fast in panic. Coulling's "helter skelter" image. Use this as **context, not a signal**:
- Expect down legs to be steeper and shorter than up legs.
- A buying climax at the bottom usually follows a fast, waterfall decline.
- Do not penalize a fast drop as "abnormal."

### 2.5 Insider psychology [Read]
Insiders (market makers, large operators) have two levers: **fear and greed**, amplified by the media. They need the public on the wrong side: buying at the top, panic-selling at the bottom. Use this for coaching notes only; it is not detectable.

### 2.6 Practice and timeframes [Read]
VPA works on all timeframes and for all trader styles. Coulling suggests about six months of daily chart reading to become fluent. Coaching text only.

### 2.7 Dark pools caveat [Read]
Coulling admits that volume is not completely unhideable: large institutions route trades through dark pools. Include this in any user-facing "limits of the method" note. Detection cannot account for it.

---

## 3. The three premier candles (and the hanging man)

Coulling names the **shooting star, hammer and long-legged doji** as her trio of premier candles [Read]. She treats every other candlestick as secondary.

### 3.1 Shape detection [Interp]
```
SHOOTING_STAR_SHAPE:
  upperWick >= 2 * body
  upperWick >= 0.5 * range
  lowerWick <= 0.15 * range
  body sits in lower third of range
  (color does not matter)

HAMMER_SHAPE:
  mirror: lowerWick >= 2 * body, lowerWick >= 0.5 * range,
  upperWick <= 0.15 * range, body in upper third

LONG_LEGGED_DOJI_SHAPE:
  body <= 0.1 * range
  upperWick >= 0.3 * range AND lowerWick >= 0.3 * range
  relRange >= 1.0                      // the legs must be long, i.e. a wide-range bar
```
Coulling considers only the **long-legged** doji significant for VPA. Small dojis and other doji variants should be ignored or labeled `MINOR_DOJI` with no bias [Read].

### 3.2 Shooting star [Read]
- **Where it matters:** after a rise or near resistance or highs. Price was pushed up, then sold back down: selling pressure.
- **It is NOT an immediate reversal signal.** It signals *potential* weakness. Its significance comes only from volume.
- **No anomaly is possible.** Volume never contradicts a shooting star; it only grades its strength. Always `verdict = VALIDATION`; vary `confidence` by volume.

| Volume | Reading | Confidence [Interp] |
|---|---|---|
| LOW | Minor weakness. After a selling climax it can be a **test of demand** (section 6.2). | 0.25 |
| AVERAGE | Relatively strong sign of weakness | 0.5 |
| HIGH | Professional selling | 0.7 |
| ULTRA_HIGH | Insiders selling heavily; significant change likely coming. Possibly part of a selling climax. | 0.85 |

- Shooting star in a **downtrend** (after a small bounce): continuation of weakness. Lower priority, same volume grading.

### 3.3 Hammer [Read]
- **Where it matters:** after a decline or near support or lows. Price was pushed down, then bought back up: buying pressure.
- **No anomaly is possible**, same as the shooting star. Volume grades strength only.

| Volume | Reading | Confidence [Interp] |
|---|---|---|
| LOW | Minor strength; any reversal likely small, little upside interest. After a buying climax it can be a **test of supply** (section 6.1). | 0.25 |
| AVERAGE | Stronger reversal signs; short-term opportunity | 0.5 |
| HIGH | Insiders buying | 0.7 |
| ULTRA_HIGH | Insiders buying heavily; a **buying climax** may be forming | 0.85 |

### 3.4 Hanging man [Read]
- **Shape:** identical to a hammer (`HAMMER_SHAPE`).
- **Context:** appears **after an uptrend / at the top**. Reading: **bearish**. The deep lower wick shows sellers were present and active.
- Coulling notes this was her own early mistake: she used to read it as strength. It is not.
- **Requires validation:** above-average volume (`relVol >= 1.0`, stronger at HIGH+). On low volume, downgrade to a weak warning.
- **Hanging man followed by a shooting star** (within a few bars, same price area) is a powerful bearish combination. Emit a combined `HANGING_MAN_SHOOTING_STAR` detection with boosted confidence.

Implementation: one shape detector, two labels. `HAMMER` if context is DOWNTREND or near support; `HANGING_MAN` if context is UPTREND or near highs.

### 3.5 Long-legged doji [Read]
- Shows indecision: a fight between buyers and sellers that ended level.
- **Unlike the hammer and shooting star, the doji CAN be an anomaly.**

| Volume | Verdict | Reading |
|---|---|---|
| LOW | **ANOMALY** | A **trap**. Low volume cannot produce a genuine wide-range battle. Likely insiders moving price to trigger stops. Do not read as indecision. |
| AVERAGE | Validation (weak) | Some indecision |
| HIGH / ULTRA_HIGH | Validation | Genuine stalemate; potential turning point. **Wait for the next bars to confirm direction.** |

- Bias: `WAIT` in all cases until later bars confirm. At a trend extreme on high volume, raise confidence that a turn is near.

### 3.6 "Upthrust" terminology note [Read]
Coulling sometimes calls a shooting star an **upthrust**. In VSA, "upthrust" means a false breakout above resistance. To avoid collisions:
- `SHOOTING_STAR` = candle shape (section 3.2).
- `UPTHRUST` (if implemented) = false breakout above a resistance level that closes back below it (section 8.6). Document both in code comments.

---

## 4. Multiple appearances rule [Read]

Single candles matter. **Repeated appearances of the same candle in the same price area increase bullish or bearish sentiment exponentially.**
- 1 occurrence = warning.
- 2 nearby = increasing sentiment.
- 3 = strong, exponentially increasing.

Detection [Interp]:
```
for each premier-candle detection at bar i:
  repeatCount = count of same type in bars [i-10, i]
                whose (high for stars / low for hammers) is within 0.5 * ATR14 of bar i's
  confidence  = min(1, base * (1 + 0.6 * (repeatCount - 1)))
```
Apply the same idea across types where they agree: hanging man + shooting star at the same top both count as bearish evidence.

---

## 5. Sequences: stopping volume, topping out volume, climaxes

These are **multi-bar** events. Detect them as windows, not single bars.

### 5.1 Stopping volume (bullish, inside a downtrend) [Read]
The brakes being applied to a falling market as insiders start absorbing selling. It usually **precedes the buying climax**.
```
context: DOWNTREND, mature (trendMaturity >= 10 bars)
window: 2–5 consecutive bars where:
  relVol >= 1.3 (HIGH+), ideally volRising
  lowerWick deepening: lowerWick >= 0.3 * range on most bars
  closeLoc rising off the lows (>= 0.35)
  spreads narrowing vs prior down bars, or down-progress per bar shrinking
bias: BULLISH (early warning, not an entry)
```
Reading: heavy volume yet price struggles to fall further. Effort without result, on the downside.

### 5.2 Topping out volume (bearish, inside an uptrend) [Read]
The mirror. As distribution builds you see a run of candles with:
- narrowing spreads,
- deep upper wicks,
- closes in the lower half of the candle,
- all on well-above-average and **rising** volume.

The final candle is typically a **shooting star**. Coulling describes the price action as **arcing over** at the top.
```
context: UPTREND, mature
window: 3–6 bars:
  relVol >= 1.3 and volRising
  upperWick >= 0.3 * range on most bars
  closeLoc <= 0.5 on most bars
  relRange trending down across the window
  last bar SHOOTING_STAR_SHAPE (boost confidence if so)
  highs flattening (new highs by < 0.25 ATR, or failing)
bias: BEARISH
```

### 5.3 Selling climax — Coulling naming = TOP, bearish [Read]
Insiders are emptying the warehouse: selling into the public's buying frenzy at the top of a bullish trend.
```
context: UPTREND, extended; often preceded by TOPPING_OUT_VOLUME
window: several bars (typically 2–6) with:
  ULTRA_HIGH or HIGH volume
  candles with deep upper wicks / shooting stars
  wide ranges but little net upward progress
  repeated failures to hold new highs
after: sideways DISTRIBUTION range forms (section 7)
bias: BEARISH
```
Often followed by a **test of demand** (section 6.2) before markdown begins.

### 5.4 Buying climax — Coulling naming = BOTTOM, bullish [Read]
Insiders are filling the warehouse: buying from the panicking public at the bottom of a bearish trend. Usually follows a fast, waterfall decline (section 2.4).
```
context: DOWNTREND, extended; often preceded by STOPPING_VOLUME
window: several bars with:
  ULTRA_HIGH or HIGH volume
  deep lower wicks / hammers
  wide ranges but little net downward progress
after: sideways ACCUMULATION range forms
bias: BULLISH
```
Often followed by a **test of supply** (section 6.1) before markup.

### 5.5 Decoys to reject [Interp, from the apps' validated test engine]
- **No prior trend:** high-volume wicky bars in the middle of a range are not a climax. Require a mature trend.
- **Volume not actually elevated:** looks like a climax shape on AVERAGE volume. Reject or downgrade.
- **Single bar:** a lone ultra-high bar is a candidate, not a climax. Climaxes are processes.

---

## 6. Testing [Read]

After a campaign (accumulation or distribution), insiders **test** whether the opposing side is still present before moving price. There are two kinds.

### 6.1 Test of supply (after accumulation, before markup — bullish)
Insiders push price down toward the accumulation lows to see whether sellers are still present.
```
context: after BUYING_CLIMAX / inside ACCUMULATION range
bar: moves down into the lower part of the range, then closes off its lows
     (HAMMER_SHAPE or narrow down bar with lower wick; closeLoc >= 0.5)
volume:
  LOW            -> TEST_OF_SUPPLY_PASSED  (no sellers left; markup likely)   bias BULLISH
  HIGH/ULTRA     -> TEST_OF_SUPPLY_FAILED  (sellers still present; more accumulation/
                                            the campaign restarts)          bias WAIT
```
Multiple tests can occur. A low-volume test after a failed one is the green light.

### 6.2 Test of demand (after distribution, before markdown — bearish)
The mirror. Insiders push price up toward the distribution highs to see whether buyers remain.
```
context: after SELLING_CLIMAX / inside DISTRIBUTION range
bar: moves up into the upper part of the range, closes off its highs
     (SHOOTING_STAR_SHAPE or narrow up bar with upper wick; closeLoc <= 0.5)
volume:
  LOW         -> TEST_OF_DEMAND_PASSED  (no buyers; markdown likely)    bias BEARISH
  HIGH/ULTRA  -> TEST_OF_DEMAND_FAILED  (buyers still present; more distribution)  bias WAIT
```

---

## 7. Market cycle state machine [Read]

Coulling uses the warehouse analogy:
1. **Accumulation:** insiders fill the warehouse at low prices. It cannot be done in one move. They repeatedly shake sellers out, like shaking fruit from a tree; each wave of panic creates a new buying opportunity. Can take days, weeks or months depending on the market and timeframe.
2. **Markup:** warehouse full; price is moved higher. The public is drawn in by greed.
3. **Distribution:** insiders empty the warehouse to the public at high prices, again over repeated waves.
4. **Markdown:** warehouse empty; price falls. Fear is used to drive the public out, setting up the next accumulation.

Suggested state machine [Interp]:
```
DOWNTREND --(STOPPING_VOLUME)--> DOWNTREND_SLOWING
          --(BUYING_CLIMAX)----> ACCUMULATION (sideways range)
ACCUMULATION --(TEST_OF_SUPPLY_PASSED + valid upside breakout)--> MARKUP
MARKUP (UPTREND) --(TOPPING_OUT_VOLUME)--> UPTREND_TIRING
                 --(SELLING_CLIMAX)-----> DISTRIBUTION (sideways range)
DISTRIBUTION --(TEST_OF_DEMAND_PASSED + valid downside breakout)--> MARKDOWN
```
Every detection should carry the current phase in `context`. Many signals only make sense in a given phase: a test only exists after a climax or inside a range.

---

## 8. Support and resistance [Read]

The biggest structural chapter. Most of a detector's real-world value comes from knowing **where** a signal occurs relative to these levels.

### 8.1 Markets mostly range [Read]
Coulling's rule of thumb: markets spend roughly **70% of the time ranging** and only about **30% trending**. A detector that sees trends everywhere is wrong. Default to RANGE when unsure.

### 8.2 Why markets consolidate [Read]
1. **Pending news:** the market waits for an announcement or data.
2. **Climax phases:** insiders filling or emptying the warehouse (accumulation and distribution).
3. **Old price levels:** traders trapped at a previous level try to get out near break-even when price returns, creating supply (or demand) there.

Encode reason 3 as: prior congestion zones and high-volume areas become future S/R (see section 10 for volume at price).

### 8.3 Pivot highs and pivot lows [Read for concept; Interp for exact rule]
Pivots define the **ceiling** and **floor** of a congestion zone. Coulling defines a pivot as a specific three-candle combination.
```
PIVOT_HIGH at i: high(i) > high(i-1) and high(i) > high(i+1)
                 (stronger if bar i-1 is up and bar i+1 is down)
PIVOT_LOW  at i: low(i)  < low(i-1)  and low(i)  < low(i+1)
```
Note: a pivot at `i` is only *known* at `i+1`. Record `confirmedAt = i+1` to respect the no-look-ahead rule.
Not every zone has both a clear ceiling and floor; when one is missing, infer it from nearby pivots and use judgment.

### 8.4 Congestion zone detection [Interp]
```
zone over window K >= 10 bars:
  (maxHigh - minLow) <= 3.0 * ATR14
  at least 2 pivot highs near the ceiling (within 0.5 ATR) and/or 2 pivot lows near the floor
ceiling = cluster of pivot highs; floor = cluster of pivot lows
track zone.duration (cause and effect, section 2.1)
```

### 8.5 S/R are rubber bands, not steel rods [Read]
Levels have give. Price can poke through briefly and return without the level being broken. Detectors must use **zones** (level ± about 0.25–0.5 ATR), not exact prices, and judge breaks on closes, not wicks.

### 8.6 Valid breakout criteria [Read]
```
VALID_BREAKOUT_UP at bar i:
  close(i) > ceiling + 0.25 * ATR14      // a clear close above, not one tick
  relVol(i) >= 1.5 and volRising          // well above average and rising
then ideally:
  PULLBACK to old ceiling on LOW / falling volume -> healthy; old ceiling now acting as support
```
Mirror for `VALID_BREAKOUT_DOWN` below the floor.

### 8.7 Fake-out / low-volume breakout [Read]
A breakout on low volume is not genuine. It is a classic insider trap to pull traders in on the wrong side or trigger stops.
```
FALSE_BREAKOUT:
  price closes beyond the zone but relVol < 1.0
  (or: wick beyond the zone, close back inside — the shape-level upthrust/spring)
bias: opposite to the break direction, or WAIT
```
If the bar closes back inside the zone with a long wick beyond it:
- above the ceiling → `UPTHRUST` (bearish), see section 3.6;
- below the floor → `SPRING` (bullish).

### 8.8 S/R flip [Read]
After a valid breakout, the old ceiling becomes the new floor, and vice versa. That level is the natural place for a stop. Store flipped levels and watch for tests of them.

---

## 9. Trends, timeframes and chart patterns

### 9.1 Dominant trend and multiple timeframes [Read]
- Trading **with** the dominant trend: lower risk, likely longer hold.
- Trading **against** it: higher risk, shorter hold.
- Use a **slower timeframe as the benchmark** for the dominant trend. Coulling typically watches three timeframes together. Her analogy treats faster timeframes as ripples and waves on top of the slower tide [Book].

Implementation [Interp]: compute `trendState` on a slower aggregation (e.g. 4× the base timeframe, like the Tape Reader's 15m → 1h) and add `dominantTrend` to every detection. Signals agreeing with it get a confidence boost; counter-trend signals get flagged.

### 9.2 Dynamic trends and trend lines [Book]
Coulling builds trends from pivots: higher pivot highs and higher pivot lows define an uptrend; trend lines are drawn through pivots. The same validation rule applies: each new leg should be supported by volume (section 2.3).

### 9.3 Chart patterns [Read]
All of these are congestion structures. Breakouts must meet section 8.6; low-volume breaks are suspect (section 8.7).

| Pattern | Geometry | Reading |
|---|---|---|
| **Falling triangle** | Lower pivot highs + flat floor | Weakness. Expect a downside break. |
| **Rising triangle** | Higher pivot lows + flat ceiling | Bullish. Once the ceiling clears on volume, it becomes support. |
| **Pennant** | Lower highs + higher lows, converging | A coiled spring. Direction unclear: **wait** for a breakout with volume. |
| **Triple top / triple bottom** | Same level tested three times | Each test weakens the level. Two plays: counter-trend entry on a test, or breakout entry on a validated breach. |

Detection [Interp]: fit lines through the last 3+ pivot highs and 3+ pivot lows in a zone. Flat = slope within ±0.05 ATR/bar. Converging = slopes have opposite signs. Triple top = 3 pivot highs within 0.5 ATR of each other.

---

## 10. Volume at price [Book]

Coulling also covers **volume at price (VAP)**: a horizontal histogram of how much volume traded at each price level, rather than at each time.
- **High-volume nodes** = prices where the market spent effort and agreed on value. They act as **support/resistance** and connect directly to section 8.2 reason 3 (trapped traders).
- **Low-volume areas** = prices the market moved through quickly. Price tends to move fast through them again.
- A breakout from a high-volume node into a low-volume area tends to travel.

Approximation from OHLCV bars [Interp]: distribute each bar's volume across its high–low range (uniformly, or weighted toward the close), bin by price, and sum over the lookback. Report the highest node and the main nodes as candidate S/R.

---

## 11. Scoring and combining evidence [Interp]

Suggested confidence model for any detection:
```
confidence = base(signal, volumeClass)
           × contextFit        // right place in the trend/phase? (0.3 if wrong place, 1.0 if right)
           × repeatBoost       // section 4
           × locationBoost     // at S/R or a VAP node: 1.2; in the middle of nowhere: 0.8
           × dominantTrendFit  // section 9.1: with = 1.1, against = 0.8
clamp to [0, 1]
```
Emit `bias = WAIT` when:
- the signal is a long-legged doji (until confirmed),
- context conflicts (e.g. a bullish signal in a strong downtrend with no climax or stopping volume),
- a breakout lacks volume,
- confidence is below about 0.35.

**"Wait" is a valid output.** Most bars produce no actionable signal. A detector that fires constantly is broken.

---

## 12. Coverage checklist

Concepts this spec expects detectors (or context fields) for:

**Bar level:** validation/anomaly matrix · shooting star (4 volume grades) · hammer (4 grades) · hanging man · long-legged doji (incl. low-volume trap) · hanging man + shooting star combo · multiple appearances.

**Sequence level:** stopping volume · topping out volume · selling climax (top) · buying climax (bottom) · test of supply (pass/fail) · test of demand (pass/fail).

**Trend level:** rising price + falling volume · falling price + falling volume · wave-by-wave volume comparison · dominant trend on slower timeframe · pivots and trend lines.

**Structure level:** congestion zones and duration · pivot highs/lows · valid breakout · false/low-volume breakout · upthrust / spring · S/R flip · falling triangle · rising triangle · pennant · triple top/bottom · volume-at-price nodes · cycle phase state machine.

---

## Appendix A — Concepts in the existing apps that are VSA, not core Coulling

The VPA apps teach a few labels from Tom Williams' VSA tradition. Coulling's framework covers the same ideas through the validation/anomaly lens, but not always by these names. Keep them only if you want them; map them as follows.

| App label | Nearest Coulling concept |
|---|---|
| No Demand | Up bar on low volume, narrow spread, in an uptrend: trend-level weakness (2.3) and test-of-demand logic (6.2) |
| No Supply | Down bar on low volume, narrow spread: test-of-supply logic (6.1) |
| Effort vs Result | Wyckoff's third law and the anomaly matrix (2.1, 2.2) |
| Spring / Upthrust | False breakout below the floor / above the ceiling (8.7) |
| Bullish / Bearish Engulfing | Secondary candle patterns; Coulling centers the three premier candles |

**Climax names in the apps are currently Wyckoff/VSA convention.** Under this spec they swap (see section 0).

## Appendix B — Honest limits to show users
- VPA is interpretive. Thresholds here are our choices, not Coulling's.
- Dark pools hide some institutional volume.
- Signals describe probabilities and context, not predictions. Short-term direction is close to a coin flip without them, and only modestly better with them.
- Synthetic-data practice avoids look-ahead bias but does not prove an edge on live markets.
