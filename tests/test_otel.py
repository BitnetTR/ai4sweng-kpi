import pytest

otel_sdk = pytest.importorskip("opentelemetry.sdk.metrics")

from opentelemetry import metrics as otel_metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from ai4sweng import KPI
from ai4sweng import otel as ai4sweng_otel


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
    KPI.KIO7.code_generation_speed.record(95.0, source="pipeline-x")

    attrs = _collect_attributes(metric_reader, "ai4sweng.kpi.code_generation_speed")
    assert any(a["kio.id"] == "KIO7" and a["source"] == "pipeline-x" for a in attrs)


def test_record_uses_kio_from_the_namespace_it_was_accessed_through(metric_reader):
    KPI.KIO3.code_generation_speed.record(80.0, source="ci")

    attrs = _collect_attributes(metric_reader, "ai4sweng.kpi.code_generation_speed")
    assert any(a["kio.id"] == "KIO3" and a["source"] == "ci" for a in attrs)


def test_record_missing_required_attribute_raises():
    with pytest.raises(ValueError, match="source"):
        KPI.KIO7.code_generation_speed.record(95.0)


def test_record_counter_instrument(metric_reader):
    KPI.KIO2.customer_reported_issues.record(3, source="qa")

    attrs = _collect_attributes(metric_reader, "ai4sweng.kpi.customer_reported_issues")
    assert any(a["kio.id"] == "KIO2" and a["source"] == "qa" for a in attrs)


def test_record_gauge_instrument(metric_reader):
    KPI.KIO13.adoption_rate.record(0.42, source="telemetry-service")

    attrs = _collect_attributes(metric_reader, "ai4sweng.kpi.adoption_rate")
    assert any(a["kio.id"] == "KIO13" and a["source"] == "telemetry-service" for a in attrs)


def test_record_without_otel_installed_gives_actionable_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fail_on_otel(name, *args, **kwargs):
        if name == "opentelemetry" or name.startswith("opentelemetry."):
            raise ImportError("simulated: opentelemetry not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_on_otel)
    with pytest.raises(ImportError, match=r"ai4sweng\[otel\]"):
        KPI.KIO7.code_generation_speed.record(95.0, source="pipeline-x")
