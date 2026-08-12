import pytest

from ai4sweng import KPI


def test_list_kios_includes_declared_kios():
    kios = KPI.list_kios()
    assert "KIO1" in kios
    assert "KIO13" in kios
    assert kios == sorted(kios, key=lambda k: int(k.replace("KIO", "")))


def test_kio_attribute_access_returns_metric():
    metric = KPI.KIO7.code_generation_speed
    assert metric.id == "1.1"
    assert metric.name == "Code generation speed"
    assert "KIO7" in metric.kios


def test_metric_shared_across_multiple_kios():
    assert KPI.KIO2.code_generation_speed.id == KPI.KIO4.code_generation_speed.id == "1.1"


def test_kio_with_no_metrics_is_empty_namespace():
    assert len(KPI.KIO5) == 0
    assert list(KPI.KIO5) == []


def test_unknown_kio_raises_attribute_error():
    with pytest.raises(AttributeError):
        KPI.KIO99


def test_get_kio_metrics_returns_dict_keyed_by_attr():
    metrics = KPI.get_kio_metrics("KIO8")
    assert "lifecycle_energy_reduction" in metrics
    assert "cross_architecture_build_success_rate" in metrics


def test_get_kio_metrics_unknown_kio_raises_key_error():
    with pytest.raises(KeyError):
        KPI.get_kio_metrics("KIO99")


def test_get_kpi_by_id():
    kpi = KPI.get_kpi("9.2")
    assert kpi.name == "Technical debt reduction"
    assert kpi.attr == "technical_debt_reduction"


def test_get_kpi_unknown_id_raises_key_error():
    with pytest.raises(KeyError):
        KPI.get_kpi("99.9")


def test_list_kpis_returns_all_entries():
    all_kpis = KPI.list_kpis()
    ids = {k.id for k in all_kpis}
    assert "1.1" in ids
    assert "8.3" in ids
    assert len(all_kpis) == len(ids)


def test_reload_after_editing_metrics_file(tmp_path, monkeypatch):
    KPI.reload()
    assert KPI.KIO7.code_generation_speed.id == "1.1"


def test_metric_carries_otel_instrumentation_contract():
    spec = KPI.KIO7.code_generation_speed.otel
    assert spec.name == "ai4sweng.kpi.code_generation_speed"
    assert spec.instrument == "Histogram"
    assert spec.unit == "s"
    assert spec.required_attributes == ["kio.id", "source"]


def test_every_kpi_has_a_valid_otel_instrument():
    valid = {"Counter", "UpDownCounter", "Histogram", "Gauge"}
    for kpi in KPI.list_kpis():
        assert kpi.otel is not None, f"{kpi.id} has no otel spec"
        assert kpi.otel.instrument in valid
        assert "kio.id" in kpi.otel.required_attributes


def test_kio_id_is_bound_from_the_accessed_namespace_not_typed_by_hand():
    assert KPI.KIO2.code_generation_speed._kio_id == "KIO2"
    assert KPI.KIO4.code_generation_speed._kio_id == "KIO4"


def test_for_kio_binds_a_kpi_fetched_by_id():
    bound = KPI.get_kpi("1.1").for_kio("KIO3")
    assert bound._kio_id == "KIO3"


def test_for_kio_rejects_unassociated_kio():
    with pytest.raises(ValueError):
        KPI.get_kpi("1.1").for_kio("KIO13")
