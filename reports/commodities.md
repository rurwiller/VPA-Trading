# Gold (GLD) and silver (SLV) against the Mag 7 group

Same tests as the other reports, same order mechanics (stop-entry through the candle, stop beyond the wick, 1R target). Cells are average net result and (count). Mag7+ = AAPL MSFT GOOGL AMZN NVDA META TSLA SPY QQQ AMD.


## Candle rules (9m + 15m), avg R per trade

| set                                                     | GLD before   | GLD after    | SLV before   | SLV after    | Mag7+ before    | Mag7+ after    |
|:--------------------------------------------------------|:-------------|:-------------|:-------------|:-------------|:----------------|:---------------|
| pivot-wick shorts at a 1h/4h/D gap (the scanner's rule) | -0.069 (548) | -0.105 (416) | -0.127 (539) | -0.137 (426) | -0.095 (5,160)  | -0.043 (3,294) |
| pivot-wick shorts, no gap needed                        | -0.146 (940) | -0.099 (645) | -0.180 (841) | -0.144 (641) | -0.117 (10,146) | -0.072 (6,527) |
| pivot-wick longs at a gap (volume >= 3x)                | -0.223 (68)  | -0.173 (63)  | +0.112 (71)  | +0.016 (76)  | -0.278 (187)    | -0.085 (187)   |
| old live rules, both sides, at a gap                    | -0.202 (651) | -0.117 (497) | -0.186 (545) | -0.083 (455) | -0.074 (4,548)  | -0.077 (3,290) |
| relaxed shape + pivot, shorts at a gap                  | -0.100 (419) | -0.087 (303) | -0.095 (387) | -0.151 (340) | -0.095 (3,882)  | -0.029 (2,494) |
| relaxed shape + pivot, longs at a gap                   | -0.217 (470) | -0.133 (375) | -0.177 (411) | -0.124 (357) | -0.070 (4,227)  | -0.076 (2,851) |

Average cost per trade in R (higher = costs eat more of each trade): GLD 0.150, SLV 0.093, Mag7+ 0.076

## EMA + gap bounce (9m + 15m candles), avg R per trade

| set                                             | GLD before   | GLD after    | SLV before   | SLV after    | Mag7+ before    | Mag7+ after    |
|:------------------------------------------------|:-------------|:-------------|:-------------|:-------------|:----------------|:---------------|
| pivot-wick candle at an EMA inside a gap, long  | -0.291 (47)  | +0.013 (24)  | -0.149 (53)  | +0.253 (33)  | -0.006 (611)    | -0.110 (351)   |
| pivot-wick candle at an EMA inside a gap, short | -0.221 (42)  | -0.120 (37)  | -0.272 (45)  | -0.064 (39)  | -0.094 (541)    | -0.071 (360)   |
| every pivot-wick candle, long                   | -0.201 (919) | -0.152 (639) | -0.136 (773) | -0.114 (608) | -0.063 (10,066) | -0.090 (6,313) |
| every pivot-wick candle, short                  | -0.146 (940) | -0.099 (645) | -0.180 (841) | -0.144 (641) | -0.117 (10,146) | -0.072 (6,527) |

## Limit order at the daily EMA (stop and target 1 ATR), avg R

| set                       | GLD before   | GLD after   | SLV before   | SLV after   | Mag7+ before   | Mag7+ after   |
|:--------------------------|:-------------|:------------|:-------------|:------------|:---------------|:--------------|
| touch dEMA9 + gap, long   | -0.090 (90)  | -0.058 (65) | -0.225 (80)  | -0.110 (46) | -0.047 (729)   | -0.123 (511)  |
| touch dEMA9 + gap, short  | -0.276 (79)  | -0.095 (49) | -0.423 (77)  | -0.054 (51) | -0.082 (699)   | -0.059 (464)  |
| touch dEMA21 + gap, long  | -0.040 (39)  | +0.128 (36) | -0.209 (48)  | -0.043 (33) | -0.026 (470)   | -0.099 (340)  |
| touch dEMA21 + gap, short | -0.299 (51)  | -0.229 (35) | -0.214 (56)  | -0.055 (34) | -0.004 (501)   | -0.030 (342)  |

## Pivot wick + 15/9/5 oscillators elevated, avg R per trade

| set                                        | GLD before     | GLD after      | SLV before     | SLV after      | Mag7+ before    | Mag7+ after     |
|:-------------------------------------------|:---------------|:---------------|:---------------|:---------------|:----------------|:----------------|
| every pivot-wick candle (5m/9m/15m), short | -0.158 (2,055) | -0.172 (1,486) | -0.159 (1,812) | -0.157 (1,415) | -0.116 (21,857) | -0.102 (14,204) |
| oscillators 15/9/5 all >= 80, short        | -0.126 (132)   | -0.256 (115)   | -0.072 (90)    | -0.153 (77)    | -0.074 (1,504)  | -0.126 (935)    |
| oscillators all <= 20, long                | -0.278 (138)   | -0.221 (107)   | -0.177 (93)    | -0.111 (82)    | -0.124 (1,594)  | -0.111 (1,023)  |
| oscillators >= 80 + volume >= 2x, short    | -0.433 (26)    | +0.006 (29)    | -0.102 (19)    | -0.333 (12)    | -0.018 (215)    | -0.088 (155)    |
| oscillators <= 20 + volume >= 2x, long     | -0.136 (29)    | -0.297 (34)    | -0.368 (21)    | -0.123 (25)    | -0.134 (194)    | -0.129 (151)    |

## Day-level strategies, average bps per ticker-day (net of costs unless marked)

| set                                                 | GLD before   | GLD after    | SLV before   | SLV after    | Mag7+ before   | Mag7+ after    |
|:----------------------------------------------------|:-------------|:-------------|:-------------|:-------------|:---------------|:---------------|
| momentum into the close (day so far -> last 30 min) | -0.611 (733) | -0.514 (502) | -4.186 (734) | -3.520 (502) | -0.725 (7,354) | -3.873 (5,012) |
| trend-day breakout (noise band), net                | +0.194 (733) | +0.173 (502) | -2.425 (734) | -3.992 (502) | +4.313 (7,354) | -0.314 (5,012) |
| trend-day breakout, before costs                    | +1.875 (733) | +1.803 (502) | +0.071 (734) | -1.479 (502) | +6.084 (7,354) | +1.347 (5,012) |

Breakout Sharpe ratio (per ticker, annualised) and how often it trades:

| group   |   breakout Sharpe before | share of days with a trade before   |   breakout Sharpe after | share of days with a trade after   |
|:--------|-------------------------:|:------------------------------------|------------------------:|:-----------------------------------|
| GLD     |                      0.1 | 58%                                 |                    0.06 | 57%                                |
| SLV     |                     -0.7 | 57%                                 |                   -0.6  | 58%                                |
| Mag7+   |                      0.7 | 60%                                 |                   -0.05 | 58%                                |

How big a typical day is (average absolute open-to-close move) and the round-trip cost used:

| ticker   |   avg |open->close| % |   cost bps |
|:---------|----------------------:|-----------:|
| GLD      |                  0.49 |        2   |
| SLV      |                  0.99 |        3.1 |
| TSLA     |                  2.3  |        2.5 |
| SPY      |                  0.62 |        2   |
| QQQ      |                  0.87 |        2   |
| AAPL     |                  1.07 |        2   |
