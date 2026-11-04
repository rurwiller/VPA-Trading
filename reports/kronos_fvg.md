# Kronos filter: premier candles and climaxes at 1h / 4h / D fair value gaps

600 signals since 2025-11-01, traded with Coulling's bias; exit +0.3% target / 0.5% stop. Kronos p_target = share of its paths hitting +0.3% first (random walk 62.5%).

## All

| family   |   n |   hit +0.3% % |   avg % after cost |   2se |   Kronos p_target |
|:---------|----:|--------------:|-------------------:|------:|------------------:|
| climax   | 300 |          56.3 |             -0.052 | 0.044 |             0.721 |
| premier  | 300 |          52.3 |             -0.056 | 0.043 |             0.571 |

## By Kronos p_target

|                              |   n |   hit +0.3% % |   avg % after cost |   2se |   Kronos p_target |
|:-----------------------------|----:|--------------:|-------------------:|------:|------------------:|
| ('climax', '(-0.001, 0.5]')  |  68 |          57.4 |             -0.044 | 0.092 |             0.29  |
| ('climax', '(0.5, 0.625]')   |  22 |          45.5 |             -0.157 | 0.166 |             0.566 |
| ('climax', '(0.625, 0.75]')  |  46 |          65.2 |              0.002 | 0.107 |             0.699 |
| ('climax', '(0.75, 1.0]')    | 164 |          54.9 |             -0.056 | 0.059 |             0.928 |
| ('premier', '(-0.001, 0.5]') | 137 |          58.4 |             -0.025 | 0.062 |             0.291 |
| ('premier', '(0.5, 0.625]')  |  19 |          47.4 |             -0.025 | 0.168 |             0.582 |
| ('premier', '(0.625, 0.75]') |  43 |          41.9 |             -0.163 | 0.116 |             0.696 |
| ('premier', '(0.75, 1.0]')   | 101 |          49.5 |             -0.058 | 0.074 |             0.895 |

## Keep only p_target >= 0.625 (better than a random walk)

|          |   n |   hit +0.3% % |   avg % after cost |   2se |   Kronos p_target |
|:---------|----:|--------------:|-------------------:|------:|------------------:|
| kept     | 356 |          52.8 |             -0.062 | 0.04  |             0.859 |
| rejected | 244 |          56.6 |             -0.042 | 0.048 |             0.335 |

## Rank correlation with the real result

|          |   spearman |
|:---------|-----------:|
| p_target |      0.038 |
| p_dir_1h |      0.018 |
