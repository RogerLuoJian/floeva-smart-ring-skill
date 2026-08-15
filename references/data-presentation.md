# Floeva health data presentation contract

Use this contract after a successful health-data request and before answering
the user. The API response remains the source of numeric facts; this contract
controls hierarchy, formatting, comparison, and tone.

## 1. Build a calm information hierarchy

Present only sections supported by the response, in this order:

1. **Headline** — state the date or range and one grounded observation in one
   or two sentences.
2. **At a glance** — show up to four high-value metrics in one compact Markdown
   table. Prefer Flow, sleep duration, resting heart rate or HRV, and steps when
   available and relevant.
3. **Pattern** — show a dated trend, comparison, or rhythm breakdown only when
   there are enough comparable values.
4. **What supports this** — add the smallest useful detail table, such as sleep
   stages, Flow rhythms, or daily heart-rate ranges.
5. **Data coverage** — identify missing, partial, anomalous, or non-personalized
   inputs once.
6. **Gentle next step** — offer zero to three evidence-backed ideas. Omit this
   section when the data does not support a useful action or the user asked only
   for values.

Do not dump raw JSON, repeat the same value in several sections, or create a
section whose only content is “no data.” Answer in the user's language.

## 2. Format metrics consistently

Use human-readable labels instead of API field names. Put units beside values,
not in a separate legend.

| Metric | Display |
| --- | --- |
| Flow and rhythm scores | Whole number, for example `78` |
| Duration | `7 h 42 min` / `7 小时 42 分` |
| Heart rate | Whole `bpm` |
| HRV | Whole `ms` |
| Steps | Grouped integer, for example `8,420 步` |
| Distance | One decimal `km` unless precision matters |
| Temperature | One decimal `°C` |
| Sleep efficiency and coverage | Whole percentage |
| Calories | Whole `kcal`; label as a device estimate when interpreted |

Keep tables to five columns or fewer. Right-align numeric columns when Markdown
allows it. Use short date labels only after stating the full date range. Avoid
decorative emoji rows, ASCII boxes, and color-only meaning; they wrap poorly and
reduce accessibility.

## 3. Treat missingness as information

- Render `null`, an absent field, an empty series, or an explicit false
  availability flag as `未记录` / `not recorded` or `暂无数据` / `no data yet`.
- Keep a recorded numeric zero as `0`. Never turn missing sensor data into zero.
- Some legacy tool fields normalize an unavailable optional value to zero,
  including step distance/calories, sleep-stage minutes, and workout optional
  totals. Do not describe those zeros as confirmed measurements unless another
  availability field or related record supports that interpretation. Prefer the
  null-preserving daily summary for an overview.
- Treat `has_sleep_data`, `has_activity_data`, `available`, `is_outlier`,
  `sample_count`, and returned messages as part of the evidence.
- If a metric has sparse samples or fewer dated values than the requested range,
  state the valid count, such as `5/7 天有记录`.
- When `baseline.is_personalized` is false, describe comparisons as general
  context, not the user's established norm. Mention `days_of_data` when useful.
- When every requested metric is absent, lead with a friendly empty state and
  suggest syncing or wearing the ring; do not render an empty dashboard.

## 4. Show trends without overstating them

Use a sparkline only for three or more ordered, comparable numeric values:

```text
近 7 天步数  5,420 → 6,180 → 7,030 → 6,740 → 8,120 → 7,860 → 8,420
趋势         ▁▂▄▃▇▆█
```

Generate each block from the series minimum and maximum. If all values are
equal, use the same middle block for every point. A sparkline communicates
shape, not clinical significance; keep the numeric range or daily table nearby
when exact values matter.

For two comparable points, show an absolute delta and the dates. Use arrows only
as direction markers, never as automatic “good” or “bad” judgments. Prefer
phrases such as “比近 7 天均值高 6 bpm” over “heart rate got worse.” Do not claim
improvement, recovery, readiness, or causation from an earliest-to-latest change.

Compare against a personal baseline only when the response marks it personalized
and exposes the matching baseline field. Do not combine incompatible measures,
different periods, or different source semantics into one trend.

## 5. Present common Floeva responses

### Health overview

Use this compact skeleton and omit unsupported columns:

```markdown
## 今天的身体节奏 · 8 月 15 日

昨晚的睡眠记录比较完整；今天的活动仍在累积。下面是目前最值得关注的几项。

| Flow | 睡眠 | 静息心率 | 步数 |
| ---: | ---: | ---: | ---: |
| 78 | 7 小时 42 分 | 58 bpm | 8,420 步 |

### 近 7 天

| 指标 | 最近值 | 个人参考 | 观察 |
| --- | ---: | ---: | --- |
| HRV | 46 ms | 43 ms | 接近你近期的范围 |
| 步数 | 8,420 步 | 7,760 步/天 | 比近期均值多 660 步 |

> 数据覆盖：心率 7/7 天，步数 6/7 天；个性化基线基于 21 天数据。
```

Treat every number above as a layout example only. Never reuse it as user data.

### Flow detail

Lead with the server-published Flow score and status. Then show the three
rhythms in a small table:

```markdown
| 节律 | 分数 | 主要依据 |
| --- | ---: | --- |
| 休息节律 | 82 | 睡眠时长与连续性 |
| 能量节律 | 74 | 前一天活动与恢复背景 |
| 身体节律 | 未记录 | 体温数据不足 |
```

Use contributor names, values, baselines, and statuses from the response. Do
not reconstruct formulas or expose internal calculation details that the public
response does not provide. Explain the date semantics once when relevant:
sleep contributors use the Flow date, while HRV, resting heart rate, stress,
and activity contributors use the previous day.

### Single-metric trend

Start with the latest value and covered range, then add one sparkline and a
compact table only when the user needs exact daily values. For heart rate, show
daily average plus min–max and sample count. For steps, show daily values and the
API-provided average. For sleep, keep total duration and stages together rather
than judging one stage in isolation.

## 6. Keep interpretation safe and useful

- Treat Floeva as consumer wellness data, not a diagnosis or emergency monitor.
- Describe patterns with uncertainty: `看起来`, `这几天`, `在已有记录里`, or
  equivalent language in the user's language.
- Do not invent medical thresholds, zones, targets, causes, or risk labels.
- Do not label a single unusual value as an anomaly unless the response does.
- If a user reports concerning symptoms, prioritize appropriate professional or
  emergency guidance over further dashboard interpretation.
- Keep the body as a partner: offer supportive options rather than commands,
  blame, or alarmist language.
