EN English | TR [Türkçe](README.tr.md)

# ai4sweng — KPI Interface for KIO Modules

A Python package that makes the KPIs each KIO module is expected to report
accessible from a single interface. For every KIO — `KPI.KIO1`, `KPI.KIO2`,
... `KPI.KIO13` — it gives dotted access to the KPIs associated with that
module: both the metadata (definition, unit, baseline, target) and a way to
emit a correctly labeled OpenTelemetry measurement.

## Installation

From within the project (repo cloned locally):

```bash
pip install -e .
```

If you want to emit OpenTelemetry measurements (`.record()`), also install
the `otel` extra:

```bash
pip install -e ".[otel]"
```

Directly via git (how teammates can install it):

```bash
pip install "ai4sweng[otel] @ git+https://<repo-url>"
```

## Why a name alone isn't enough

Getting a metric name right isn't enough to get it reported correctly: the
exact same value can silently fail to show up on a dashboard — or show up
wrong — if it's emitted with the wrong instrument kind (a Histogram recorded
as a Counter, or vice versa) or with a missing attribute (is `kio.id` a
resource attribute or a per-metric one? is `source` present?). This package
carries, for every KPI, not just a name but **name + unit + OTel instrument
kind + the required attribute keys**, together, and optionally provides a
`.record()` helper that enforces them.

`kio.id` is deliberately a **per-datapoint attribute, not a resource
attribute**, because a single KPI can be tied to more than one KIO (e.g.
`code_generation_speed` → KIO2, KIO3, KIO4, KIO7). When you record a metric
through `KPI.KIO3.<metric>`, this package attaches `kio.id="KIO3"`
**automatically** — a developer never types it by hand, so it can't be
mistyped or omitted.

## Usage

```python
from ai4sweng import KPI

# List every declared KIO
print(KPI.list_kios())
# ['KIO1', 'KIO2', ..., 'KIO13']

# Access a metric's metadata through KIO7
metric = KPI.KIO7.code_generation_speed
print(metric.id)          # "1.1"
print(metric.name)        # "Code generation speed"
print(metric.definition)
print(metric.unit)        # "% of baseline duration"  (business/reporting unit)
print(metric.baseline)    # "100% (~100-120 min)"
print(metric.target)      # "≤ 70% (~30% reduction)"
print(metric.kios)        # ["KIO2", "KIO3", "KIO4", "KIO7"]

# OTel instrumentation contract
print(metric.otel.name)                 # "ai4sweng.kpi.code_generation_speed"
print(metric.otel.instrument)           # "Histogram"
print(metric.otel.unit)                 # "s"          (raw OTel measurement unit)
print(metric.otel.required_attributes)  # ["kio.id", "source"]
```

### Recording a measurement (requires `pip install ai4sweng[otel]`)

```python
from ai4sweng import KPI

# kio.id="KIO7" is attached automatically because it was accessed via KIO7.
KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline")

# A Counter-kind metric
KPI.KIO2.customer_reported_issues.record(1, source="qa-bot")

# A Gauge-kind metric
KPI.KIO13.adoption_rate.record(0.42, source="telemetry-service")

# A missing required attribute raises a clear error:
KPI.KIO7.code_generation_speed.record(95.0)
# ValueError: Missing required attribute(s) for 'ai4sweng.kpi.code_generation_speed': source. ...

# .record() also raises an actionable error if a metric has no 'otel' block
# in metrics.json, or if opentelemetry-api isn't installed.
```

If you fetch a KPI directly by id via `KPI.get_kpi("1.1")`, `.record()` isn't
available on it — which KIO it should be tagged with is ambiguous — so bind
it first with `.for_kio("KIO3")`:

```python
kpi = KPI.get_kpi("1.1").for_kio("KIO3")
kpi.record(95.0, source="ci-pipeline")
```

Other helpers:

```python
# Iterate every metric tracked by one KIO
for m in KPI.KIO7:
    print(m)

# Get a KIO's metrics as a dict
metrics = KPI.get_kio_metrics("KIO8")

# List every KPI
all_kpis = KPI.list_kpis()

# Reload metrics.json after editing it
KPI.reload()
```

## Editing the metrics

All KPI definitions live in a single file:
[`ai4sweng/metrics.json`](ai4sweng/metrics.json). Each KPI lists every KIO
it's associated with in its `kios` array — there's no need to duplicate a
KPI's definition once per KIO, the package builds that mapping automatically.

**Every field in `metrics.json` (name, definition, unit, baseline, target)
must be in English.** This file is the data/code layer and is consumed by
dashboards, other services, and potentially external audiences — it should
stay language-neutral. Keep any Turkish explanations to this README and code
comments only.

To add a new KPI, append an object in this shape to the list:

```json
{
  "id": "10.1",
  "name": "Example metric name",
  "attr": "example_metric_name",
  "definition": "What this metric measures.",
  "unit": "unit",
  "baseline": "baseline value",
  "target": "target value",
  "kios": ["KIO3", "KIO7"],
  "otel": {
    "name": "ai4sweng.kpi.example_metric_name",
    "instrument": "Histogram",
    "unit": "s",
    "required_attributes": ["source"]
  }
}
```

- `attr`: the name it will be exposed as on the Python side,
  `KPI.KIO3.<attr>` (must be a valid identifier). Auto-derived from `name` if
  omitted.
- `kios`: the list of KIOs this KPI is associated with. A KPI can belong to
  more than one KIO.
- `otel.instrument`: one of `Counter`, `UpDownCounter`, `Histogram`, or
  `Gauge` (`Gauge` requires `opentelemetry-api>=1.23`).
- `otel.unit`: the raw OTel/UCUM-style measurement unit (e.g. `"s"`, `"J"`,
  `"1"`, `"{issue}"`) — don't confuse this with the business-facing `unit`
  field from the KPI table.
- `otel.required_attributes`: attribute keys, other than `kio.id`, that the
  caller must supply to `.record()` (`kio.id` is always injected
  automatically, no need to list it here).
- The `kios` array at the top of the file declares which KIOs exist even
  before they have any metrics assigned (`KPI.list_kios()` and `KPI.KIOx`
  access are both driven by it).

You don't need to restart anything after editing — just call `KPI.reload()`.

**The `otel.instrument` / `otel.unit` values shipped here are proposed
defaults based on each metric's measurement semantics** (durations →
Histogram, point-in-time ratios/scores → Gauge, discrete event counts →
Counter/UpDownCounter). Review and adjust them to match your actual
telemetry backend — the schema is intentionally easy to edit.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_otel.py` exercises the recording path end-to-end against a real
`InMemoryMetricReader` (correct instrument kind, correct attributes) when
`opentelemetry-sdk` is installed.
