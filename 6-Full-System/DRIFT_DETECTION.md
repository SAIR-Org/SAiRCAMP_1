# Drift Detection — Mental Model, Concepts & Reference

---

## Part 1 — What Is Drift? (The Mental Model)

### Start with a doctor

A doctor trains for years on textbooks, case studies, and patients from a specific era.
They graduate and start practicing. Their knowledge was current on graduation day.

Ten years later, new diseases have emerged, new drugs exist, treatment protocols have changed.
The doctor's knowledge has *drifted* from the current reality. They're still applying
2015 reasoning to 2025 patients.

**A trained model has the same problem.**

It learned patterns from data that existed at training time. The world keeps changing.
The model's knowledge is frozen at the moment training ended.

**Drift** = the gap between what the model learned and what it's now seeing.

---

### The three types — and which one matters here

The ML literature defines three types:

**Data drift (covariate drift):**
The input distribution changed. The model sees inputs it wasn't trained on.
Example: Uber took all the short taxi trips. By 2022, taxis only serve long trips.
The model was trained on short + long. Now it only sees long. Input distribution shifted.

**Concept drift (label drift):**
The relationship between inputs and outputs changed.
Example: The same trip now takes 45% longer because of new traffic patterns.
Inputs are the same. Output (duration) is systematically higher. The model is wrong.

**Data quality drift:**
The data pipeline broke. Missing values, schema changes, null columns.
Not a model problem — a data engineering problem.

**Which type did we see in this course?**

```
2020-04: COVID hit NYC
  → 97% fewer trips (volume collapse)
  → Shorter trips (people avoiding public spaces)
  → Model accuracy dropped 80% (MAE 3.07 → 5.55)

This is ALL THREE types simultaneously:
  Volume: 7.7M → 204k (97% collapse)
  Data:   trip distance, patterns all changed (data drift)
  Concept: duration-distance relationship changed (concept drift)
```

The COVID event is the most dramatic possible example of real-world drift.
It proves the need for monitoring better than any textbook could.

---

### Why monitoring catches it — and silence doesn't

Without monitoring:
```
Jan 2020: Model deployed, working well
Apr 2020: COVID hits, model breaks → nobody knows
May 2020: Users get predictions 80% worse → nobody knows
Jun 2020: Engineer notices "something feels off" → investigate
Jul 2020: Root cause found → retrain
```
3 months of silent degradation.

With monitoring:
```
Jan 2020: Model deployed, batch scorer running monthly
Apr 2020: COVID hits, model breaks → MAE ratio = 1.81x → ALERT fires
May 2020: Alert reviewed → retrain triggered
Jun 2020: New model in production
```
One month of degradation.

**Monitoring doesn't prevent drift. It catches it before it compounds.**

---

## Part 2 — Detecting Drift

### What we tried and rejected: the σ formula

The standard textbook approach for detecting label drift:

```python
drift_score = abs(batch_mean - train_mean) / train_std
if drift_score > 2.0:
    alert()
```

This measures how many standard deviations the batch mean is from the training mean.
In theory: if the distribution shifts by more than 2σ, it's statistically significant.

**We ran this on our data. It failed.**

```
train_mean = 13.01 min
train_std  = 10.03 min   ← this is the problem

2020-04 batch_mean = 9.10 min
drift_score = abs(9.10 - 13.01) / 10.03 = 0.39   ← no alert!
```

Why did it fail? Because `train_std = 10.03 min` is enormous. Trip durations vary from
1 minute to 2 hours. The standard deviation is nearly as large as the mean. So even a
4-minute shift in the mean is only 0.39σ — statistically unremarkable.

The formula is designed for datasets where values are tightly clustered.
NYC taxi trips are not tightly clustered. The formula is the wrong tool.

---

### What we use instead: MAE ratio

```python
mae_ratio = batch_mae / train_mae
if mae_ratio > 1.5:   # MAE degraded 50%+
    alert()
```

**Why this works:**

It measures model performance directly, not distribution shift indirectly.

```
train_mae  = 3.07 min  (on 2019 holdout)
2020-04 MAE = 5.55 min  (on April 2020 data)
mae_ratio  = 5.55 / 3.07 = 1.81  → ALERT ✅
```

The threshold `1.5x` means: "if the model is 50% worse than it was at training time, alert."
This is intuitive, interpretable, and doesn't depend on distributional assumptions.

---

### Volume as a separate signal

MAE ratio catches accuracy degradation. But what about volume collapse?

April 2020: only 204,000 trips (vs 7.7M in January 2020). The model might actually
score *well* on those 204k trips (the few people who did travel had normal journeys).
MAE wouldn't alert. But the volume collapse is itself a signal — something dramatic happened.

```python
volume_alert = total_rows < 500_000
```

Together:
```python
alert = (mae_ratio > 1.5) or (total_rows < 500_000)
```

April 2020 triggers **both**:
- MAE ratio: 1.81x → yes
- Volume: 204k → yes

Two independent signals confirming the same event. More robust than either alone.

---

### Alert thresholds — how to choose them

**`1.5x` for MAE ratio:**
- `1.0x` = identical to training — too strict, noisy
- `2.0x` = double the error — too lenient, catches problems too late
- `1.5x` = 50% worse than training — meaningful degradation, actionable

**`500k` for volume:**
- January 2019: 7.7M trips
- April 2020 COVID: 204k trips (97% drop)
- `500k` is roughly 7% of normal — dramatic enough to signal something real

These thresholds are specific to this dataset. In production, you'd set them based on:
- Your model's acceptable performance range
- Your domain's expected volume variation
- Historical normal vs abnormal ranges

**The right question isn't "what's statistically significant?"
It's "what degradation is actionable for my use case?"**

---

## Part 3 — What We Actually Found

### The real drift story (from data, not theory)

```
Period   Volume        MAE      MAE ratio   Alert
───────  ──────────   ──────   ──────────  ──────
2019     7.7M/month   3.07 min  1.00x       —     (training baseline)
2020-04   204k/month   5.55 min  1.81x       ⚠️     COVID shock
2022-01  2.3M/month   3.00 min  0.97x       ✅    recovery
2024-01  2.7M/month   3.18 min  1.04x       ✅    stable new normal
```

**The story this tells:**

The world broke in April 2020. The model broke with it — 80% worse accuracy, 97% fewer trips.
Then the world rebuilt a new normal. The model recovered — not because we retrained it,
but because 2022 trip patterns aren't that different from 2019. The remaining gap
(3.00 vs 3.07) is essentially noise.

By 2024, fares went up 45% but trip durations didn't change much. Since we predict duration
not fare, the model is still good.

**The teaching moment:** not all drift is permanent. Sometimes the world fixes itself.
Sometimes you need to retrain. Monitoring tells you which situation you're in.

---

### What drifted and what didn't

```
                    2020-04       2022-01      2024-01
                    (COVID)     (new normal)  (inflation)
─────────────────  ─────────   ────────────  ───────────
Volume             ⬇️ 97%        ↗️ recovering  ↗️ growing
Duration mean      ⬇️ 9.1 min   ➡️ 12.7 min   ⬆️ 14.9 min
Trip distance      ⬇️ 2.7 mi    ➡️ 3.1 mi     ➡️ 3.3 mi
Model MAE          ⬆️ 5.55      ➡️ 3.00       ➡️ 3.18
```

The MAE spike in 2020 is real. The recovery is real.
The 2024 increase in duration mean (+2 min vs training) is interesting —
trips got longer, but the model is still accurate (MAE 3.18 ≈ training 3.07).
This shows the model generalizes reasonably to slightly longer trips.

---

## Part 4 — Connecting Concepts to Code

### The monitoring pipeline

```
batch scorer runs                    monitoring reads
──────────────                       ────────────────
core.score_month()                   sqlite3.connect("batch_results.db")
→ batch_results.db   ──────────────→ monitor.py
  (one row per period)               → health report
                                     → drift chart
```

The monitor is intentionally simple — it reads a SQLite file. No streaming,
no external services, no complex infrastructure. The complexity is in the
batch scorer (downloading + scoring millions of trips). The monitor just reads
the already-computed summary and visualizes it.

### The alert in code

```python
# core.py
MAE_RATIO_THRESHOLD = 1.5
VOLUME_THRESHOLD    = 500_000

mae_alert    = (mae / train_mae) > MAE_RATIO_THRESHOLD
volume_alert = total_rows < VOLUME_THRESHOLD
alert        = int(mae_alert or volume_alert)
```

10 lines. No external libraries. Every student understands what it checks.

### The monitoring report

```python
# monitor.py
def print_health_report(df):
    for _, row in df.iterrows():
        flag = "⚠️  ALERT" if row["alert"] else "✅ OK"
        print(f"  {row['period']}  MAE={row['mae']:.2f}  ratio={row['mae_ratio']:.2f}x  {flag}")

    if df["alert"].sum() > 0:
        print("Recommended actions:")
        print("  → investigate data distribution shift")
        print("  → consider retraining on recent data")
```

Readable. Actionable. No magic.

---

## Part 5 — What Monitoring Is NOT

This is important to state clearly for students.

**Monitoring (what we built):**
- Tracks model performance over time (MAE, accuracy)
- Detects when the model is degrading
- Fires alerts based on business-meaningful thresholds
- Runs after each batch scoring job

**Observability (not covered here):**
- Tracks system health (latency, error rates, uptime)
- Tools: Prometheus, Grafana, Datadog
- Answers: "Is the service up? Is it slow?"

**Data quality monitoring (not covered here):**
- Tracks input data health (missing values, schema drift, outliers)
- Tools: Great Expectations, dbt tests
- Answers: "Is the data pipeline broken?"

All three are important in production. This course covers model monitoring only.
The other two are MLOps concerns beyond the scope of this module.

---

## Quick Reference

```bash
# Run monitoring after batch scoring
cd 6-Full-System/monitoring
python monitor.py
# Output: health report printed, drift_chart.png saved

# Point at a custom DB
python monitor.py --db /path/to/batch_results.db

# Query drift data directly
python -c "
import sqlite3, pandas as pd
df = pd.read_sql('SELECT * FROM batch_results ORDER BY year, month',
                 sqlite3.connect('../batch/batch_results.db'))
print(df[['year','month','mae','mae_ratio','alert']].to_string(index=False))
"
```

### Alert thresholds summary

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| MAE ratio | > 1.5x | 50% worse than training → actionable degradation |
| Volume | < 500k/month | ~7% of normal 2019 volume → dramatic collapse |
| σ formula | rejected | train_std=10min too large, absorbs real shifts |
