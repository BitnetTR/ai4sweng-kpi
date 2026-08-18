"""A few examples for exploring the ai4sweng KPI package. Run with:

    python examples/quickstart.py
"""

from ai4sweng import KPI


# 1) List every declared KIO
print("KIOs:", KPI.list_kios())

# 2) Which KPIs are available for a given KIO
print("Attribute names:", dir(KPI.KIO2))

# 3) Full details of each metric tracked by KIO2
for metric in KPI.KIO2:
    print(f"\n--- {metric.attr} ---")
    print(f"  id          : {metric.id}")
    print(f"  name        : {metric.name}")
    print(f"  definition  : {metric.definition}")
    print(f"  unit        : {metric.unit}")
    print(f"  baseline    : {metric.baseline}")
    print(f"  target      : {metric.target}")
    print(f"  kios        : {metric.kios}")  # other KIOs this KPI is also associated with

# 4) Inspect a metric's OTel instrumentation contract -- shows how it will
#    actually be sent to the dashboard.
metric = KPI.KIO2.code_generation_speed

# NOTE: there are two different "names" here, don't confuse them:
print("metric.name       (business/reporting layer, the human-readable name from the D1.1 table):", metric.name)
print("metric.otel.name  (telemetry layer, the technical name kio_simulator.py actually sends)   :", metric.otel.name)
print()

print(metric.otel)
print("instrument         :", metric.otel.instrument)
print("otel name          :", metric.otel.name)
print("raw OTel unit      :", metric.otel.unit)
print("required attributes:", metric.otel.required_attributes)

# 5) Use help() for a fuller description + a runnable usage example
# help(KPI.KIO2.customer_reported_issues.record)

# 6) Record a measurement (requires: pip install ai4sweng[otel])
# try:
#     result = KPI.KIO2.code_generation_speed.record(
#         82.0, source="manual-test", llm="qwen2.5:3b", task_type="bugfix"
#     )
#     print("Recorded attributes:", result)
# except ImportError as e:
#     print("OTel not installed, skipping:", e)
