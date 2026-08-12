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

# OTel instrumentation contract -- aligned with the real kio_simulator.py
# implementation, not invented (see "Why a name alone isn't enough" below).
print(metric.otel.name)                 # "kio.codegen.duration_minutes"
print(metric.otel.instrument)           # "Histogram"
print(metric.otel.unit)                 # "min"        (raw OTel measurement unit)
print(metric.otel.required_attributes)  # ["kio.id", "source", "llm", "task_type"]
```

### Recording a measurement (requires `pip install ai4sweng[otel]`)

```python
from ai4sweng import KPI

# kio.id="KIO7" is attached automatically because it was accessed via KIO7.
KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline", llm="qwen2.5:3b", task_type="generic")

# A Counter-kind metric
KPI.KIO2.customer_reported_issues.record(1, source="qa-bot", llm="qwen2.5:3b", task_type="bugfix")

# A missing required attribute raises a clear error:
KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline")
# ValueError: Missing required attribute(s) for 'kio.codegen.duration_minutes': llm, task_type. ...

# .record() also raises an actionable error if a metric has no 'otel' block
# in metrics.json, or if opentelemetry-api isn't installed.
```

A few KPIs are realized as more than one real OTel metric — e.g. KPI 8.2
("Active usage & satisfaction") is actually two separate histograms in
`kio_simulator.py`, `kio.adoption.usage_pct` and `kio.adoption.mos_score`.
For those, pass `otel_key` to say which one you mean:

```python
KPI.KIO13.active_usage_satisfaction.record(62.0, otel_key="usage_pct", source="svc", llm="qwen2.5:3b", task_type="adoption")
KPI.KIO13.active_usage_satisfaction.record(4.1, otel_key="mos_score", source="svc", llm="qwen2.5:3b", task_type="adoption")

# Omitting otel_key when a KPI has more than one instrument raises a clear error:
KPI.KIO13.active_usage_satisfaction.record(62.0, source="svc", llm="qwen2.5:3b", task_type="adoption")
# ValueError: KPI '8.2' has multiple OTel instruments: ['usage_pct', 'mos_score']. Pass otel_key=<one of these> to .record().
```

If you fetch a KPI directly by id via `KPI.get_kpi("1.1")`, `.record()` isn't
available on it — which KIO it should be tagged with is ambiguous — so bind
it first with `.for_kio("KIO3")`:

```python
kpi = KPI.get_kpi("1.1").for_kio("KIO3")
kpi.record(95.0, source="ci-pipeline", llm="qwen2.5:3b", task_type="generic")
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

## Discoverability: docstrings, `dir()`, and IDE autocomplete

Every class and function in `ai4sweng/kpi.py` and `ai4sweng/otel.py` has a
docstring with a description and a runnable usage example. Use Python's
built-in `help()` for any of them, in a REPL or notebook:

```python
help(KPI.list_kios)
help(KPI.KIO7.code_generation_speed.record)
```

`KPI.KIO7` and `KPI.KIO7.code_generation_speed` are built dynamically from
`metrics.json`, but as **real attributes** — not resolved through
`__getattr__` magic — specifically so `dir(KPI)`, `hasattr(...)`, and
autocomplete in a Python REPL or IPython/Jupyter all see them immediately.

A code editor's autocomplete (VS Code + Pylance, PyCharm, mypy) is
different: those tools read source code statically and never execute
`_load()`, so on their own they can't know that `KPI.KIO7` exists at all.
To fix that, this package ships a generated type stub,
[`ai4sweng/__init__.pyi`](ai4sweng/__init__.pyi) (plus the
[PEP 561](https://peps.python.org/pep-0561/) `py.typed` marker), rendered
from `metrics.json` by [`scripts/gen_stubs.py`](scripts/gen_stubs.py). That
stub is what actually makes `KPI.KIO7.<Tab>` autocomplete in an editor —
**re-run it whenever you add, remove, or rename a KPI/KIO**:

```bash
python scripts/gen_stubs.py
```

`tests/test_stubs.py` fails the test suite if the committed stub ever
drifts out of sync with `metrics.json`, so a stale stub can't slip in
unnoticed.

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
  "otel": [
    {
      "name": "kio.example_metric_name",
      "instrument": "Histogram",
      "unit": "s",
      "required_attributes": ["source", "llm", "task_type"]
    }
  ]
}
```

- `attr`: the name it will be exposed as on the Python side,
  `KPI.KIO3.<attr>` (must be a valid identifier). Auto-derived from `name` if
  omitted.
- `kios`: the list of KIOs this KPI is associated with. A KPI can belong to
  more than one KIO.
- `otel`: **always a list**, even when there's only one instrument (the
  common case). List a second entry, each with its own `key`, only if this
  KPI genuinely maps to more than one real OTel metric — see KPI 8.2 in
  `metrics.json` for an example, and `.record(value, otel_key=...)` in the
  section above for how a caller picks one.
- `otel[].instrument`: one of `Counter`, `UpDownCounter`, `Histogram`, or
  `Gauge` (`Gauge` requires `opentelemetry-api>=1.23`).
- `otel[].unit`: the raw OTel/UCUM-style measurement unit (e.g. `"s"`, `"J"`,
  `"1"`, `"{issue}"`) — don't confuse this with the business-facing `unit`
  field from the KPI table.
- `otel[].required_attributes`: attribute keys, other than `kio.id`, that the
  caller must supply to `.record()` (`kio.id` is always injected
  automatically, no need to list it here). This project's convention is
  `["source", "llm", "task_type"]`, mirroring `kio_simulator.py`'s real label set.
- The `kios` array at the top of the file declares which KIOs exist even
  before they have any metrics assigned (`KPI.list_kios()` and `KPI.KIOx`
  access are both driven by it).

**Prefer real names over invented ones.** Before adding a new `otel` entry,
check whether `kio_simulator.py` (or whatever your actual telemetry producer
is) already emits this KPI under some `kio.*` metric name — copy that name/
instrument/unit exactly rather than guessing. A name that only exists in
`metrics.json` and not in production recreates the mislabeling problem this
file exists to prevent (see below).

You don't need to restart anything after editing — just call `KPI.reload()`.

**The `otel.instrument` / `otel.unit` values shipped here are proposed
defaults based on each metric's measurement semantics** (durations →
Histogram, point-in-time ratios/scores → Gauge, discrete event counts →
Counter/UpDownCounter). Review and adjust them to match your actual
telemetry backend — the schema is intentionally easy to edit.

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

The `otel.name` / `otel.instrument` / `otel.unit` / `required_attributes`
values in `metrics.json` are deliberately taken from the real, already-running
telemetry producer (`kio_simulator.py`'s `create_histogram("kio.codegen.duration_minutes", ...)`
and friends), not invented — a package name that doesn't match what
production actually emits would recreate the exact bug this file exists to
prevent. `required_attributes` mirrors the labels `kio_simulator.py` always
attaches (`kio.id`, `llm`, `task_type`, `source`).

### Resolved design questions

- **KPI 8.2 ("Active usage & satisfaction") maps to two real OTel metrics.**
  `kio_simulator.py` emits it as `kio.adoption.usage_pct` and
  `kio.adoption.mos_score` — the `otel` schema was extended to a list so
  both are represented, disambiguated by `.record(value, otel_key=...)`
  (see above). `KPIMetric.otel` stays the convenient single-spec shortcut
  for the common one-instrument case, and is `None` for KPI 8.2 specifically
  because picking one automatically would be a silent guess.
- **KPI 4.1 ("Developer productivity") lists `KIO1` as an owner**, even
  though `kio_simulator.py`'s `KIO_REAL_KPI_ROLE` map never assigns a role
  to KIO1 in practice (KIO7's `"ai-sysdev"` role is what actually emits
  `kio.dev_productivity.features_per_day` today). Decision: **kept as-is** —
  the original KPI table (D1.1) still counts KIO1 as a co-owner, and the
  simulator not having gotten around to a KIO1 container yet doesn't mean
  the catalog should drop it. `KPI.KIO1.developer_productivity` is real
  metadata with no current producer, not a bug.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_otel.py` exercises the recording path end-to-end against a real
`InMemoryMetricReader` (correct instrument kind, correct attributes) when
`opentelemetry-sdk` is installed.
