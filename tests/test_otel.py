import pytest

otel_sdk = pytest.importorskip("opentelemetry.sdk.metrics")

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from ai4sweng import KPI
from ai4sweng import otel as ai4sweng_otel
from ai4sweng.kpi import KPIMetric

# Every recordable KPI in metrics.json requires these three, plus the
# auto-injected kio.id, matching kio_simulator.py's real label set
# ({kio.id, llm, task_type, source}).
BASE_ATTRS = {"source": "pipeline-x", "llm": "qwen2.5:3b", "task_type": "generic"}


@pytest.fixture(scope="module")
def metric_reader():
    # OpenTelemetry only allows the global MeterProvider to be set once per
    # process, so this reader is shared across the whole test module.
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    otel_metrics.set_meter_provider(provider)
    return reader


@pytest.fixture(autouse=True)
def _reset_otel_cache(metric_reader):
    ai4sweng_otel.reset_cache()
    yield
    ai4sweng_otel.reset_cache()


def _collect_attributes(reader, metric_name):
    data = reader.get_metrics_data()
    if data is None:
        return []
    attrs = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name != metric_name:
                    continue
                attrs.extend(dp.attributes for dp in m.data.data_points)
    return attrs


def test_record_histogram_auto_injects_kio_id(metric_reader):
    KPI.KIO7.code_generation_speed.record(95.0, **BASE_ATTRS)

    attrs = _collect_attributes(metric_reader, "kio.codegen.duration_minutes")
    assert any(a["kio.id"] == "KIO7" and a["source"] == "pipeline-x" for a in attrs)


def test_record_uses_kio_from_the_namespace_it_was_accessed_through(metric_reader):
    KPI.KIO3.code_generation_speed.record(80.0, **{**BASE_ATTRS, "source": "ci"})

    attrs = _collect_attributes(metric_reader, "kio.codegen.duration_minutes")
    assert any(a["kio.id"] == "KIO3" and a["source"] == "ci" for a in attrs)


def test_record_missing_required_attribute_raises():
    with pytest.raises(ValueError, match="llm"):
        KPI.KIO7.code_generation_speed.record(95.0, source="pipeline-x")


def test_record_counter_instrument(metric_reader):
    KPI.KIO2.customer_reported_issues.record(3, **{**BASE_ATTRS, "source": "qa"})

    attrs = _collect_attributes(metric_reader, "kio.issue.customer_reported_count")
    assert any(a["kio.id"] == "KIO2" and a["source"] == "qa" for a in attrs)


def test_record_adoption_rate_histogram(metric_reader):
    # kio_simulator.py records adoption rate as a Histogram (kio.adoption.active_user_pct),
    # not a Gauge -- the real system doesn't use synchronous Gauge anywhere today.
    KPI.KIO13.adoption_rate.record(42.0, **{**BASE_ATTRS, "source": "telemetry-service"})

    attrs = _collect_attributes(metric_reader, "kio.adoption.active_user_pct")
    assert any(a["kio.id"] == "KIO13" and a["source"] == "telemetry-service" for a in attrs)


def test_record_gauge_instrument_code_path(metric_reader):
    # No catalog KPI is Gauge-typed today (kio_simulator.py only ever uses
    # Histogram/Counter), but ai4sweng.otel still supports Gauge -- exercised
    # here directly against a synthetic spec so that branch stays covered.
    metric = KPIMetric({
        "id": "test.gauge",
        "name": "Test gauge metric",
        "kios": ["KIO7"],
        "otel": [{"name": "test.gauge.metric", "instrument": "Gauge", "unit": "1", "required_attributes": []}],
    })
    ai4sweng_otel.emit(metric.otel, "KIO7", 0.42, {})

    attrs = _collect_attributes(metric_reader, "test.gauge.metric")
    assert any(a["kio.id"] == "KIO7" for a in attrs)


def test_record_multi_instrument_kpi_requires_otel_key():
    with pytest.raises(ValueError, match="otel_key"):
        KPI.KIO13.active_usage_satisfaction.record(62.0, **BASE_ATTRS)


def test_record_multi_instrument_kpi_with_otel_key(metric_reader):
    KPI.KIO13.active_usage_satisfaction.record(62.0, otel_key="usage_pct", **BASE_ATTRS)
    KPI.KIO13.active_usage_satisfaction.record(4.1, otel_key="mos_score", **BASE_ATTRS)

    usage_attrs = _collect_attributes(metric_reader, "kio.adoption.usage_pct")
    mos_attrs = _collect_attributes(metric_reader, "kio.adoption.mos_score")
    assert any(a["kio.id"] == "KIO13" for a in usage_attrs)
    assert any(a["kio.id"] == "KIO13" for a in mos_attrs)


def test_record_multi_instrument_kpi_rejects_unknown_otel_key():
    with pytest.raises(ValueError, match="no OTel instrument keyed"):
        KPI.KIO13.active_usage_satisfaction.record(1.0, otel_key="nonexistent", **BASE_ATTRS)


def test_record_without_otel_installed_gives_actionable_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fail_on_otel(name, *args, **kwargs):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("simulated: opentelemetry not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_otel)
    with pytest.raises(ImportError, match=r"ai4sweng\[otel\]"):
        KPI.KIO7.code_generation_speed.record(95.0, **BASE_ATTRS)
