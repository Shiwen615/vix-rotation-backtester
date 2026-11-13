# Glossary

**Signal Asset** — The index (or ratio of two indices, written A/B) whose prior-session close drives decisions (default: VIX).

**Signal Preset** — A named Signal with its own default BUY/SELL search ranges, e.g. VIX level or VIX term structure (VIX ÷ VIX3M).

**Growth Asset** — The asset bought when the Signal Asset closes strictly above the Buy Threshold (default: TQQQ).

**Defensive Asset** — The asset bought when leaving the Growth Asset (default: QQQ). Also the Benchmark.

**Buy Threshold** — Signal level that, when strictly exceeded, triggers a switch into the Growth Asset.

**Sell Threshold** — Signal level that, when strictly undercut after the Minimum Hold, triggers a switch into the Defensive Asset.

**Minimum Hold** — Calendar months a Growth Asset position must be held, counted from each new entry, before a Sell signal counts. Early signals are ignored, not deferred.

**Observation Day** — The first day of every run. Nothing is held; its signal close decides the first position.

**Rotation** — Starting after the Observation Day in the Growth Asset if the signal exceeds the Buy Threshold, otherwise in the Defensive Asset, then switching Growth ↔ Defensive until the period ends.

**Benchmark** — Buying the Defensive Asset right after the Observation Day and holding it to the end.

**Excess Return** — Rotation Return minus Benchmark Return over the same period, in percentage points.

**Return** — Performance expressed as a percentage relative to the start, never as a currency amount. There is no capital concept.

**Parameter Set** — One combination of Buy Threshold, Sell Threshold and Minimum Hold.

**Optimization** — Running every Parameter Set in user-given ranges and ranking them by Return.

