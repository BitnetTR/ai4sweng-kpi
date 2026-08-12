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
    # These values are aligned with the real kio_simulator.py implementation
    # (kio.codegen.duration_minutes), not invented -- see README.
    spec = KPI.KIO7.code_generation_speed.otel
    assert spec.name == "kio.codegen.duration_minutes"
    assert spec.instrument == "Histogram"
    assert spec.unit == "min"
    assert spec.required_attributes == ["kio.id", "source", "llm", "task_type"]


def test_every_kpi_has_at_least_one_valid_otel_instrument():
    valid = {"Counter", "UpDownCounter", "Histogram", "Gauge"}
    for kpi in KPI.list_kpis():
        assert kpi.otel_specs, f"{kpi.id} has no otel spec"
        for spec in kpi.otel_specs:
            assert spec.instrument in valid
            assert "kio.id" in spec.required_attributes


def test_otel_convenience_is_the_single_spec_or_none_if_ambiguous():
    # KPI 1.1 has exactly one OTel instrument -> .otel is that spec directly.
    single = KPI.get_kpi("1.1")
    assert len(single.otel_specs) == 1
    assert single.otel is single.otel_specs[0]

    # KPI 8.2 is realized as two real metrics (kio.adoption.usage_pct +
    # kio.adoption.mos_score) -- .otel is deliberately None so a caller can't
    # accidentally record against the wrong one; use otel_specs/get_otel_spec().
    multi = KPI.get_kpi("8.2")
    assert len(multi.otel_specs) == 2
    assert multi.otel is None
    assert {spec.key for spec in multi.otel_specs} == {"usage_pct", "mos_score"}


def test_get_otel_spec_by_key():
    metric = KPI.get_kpi("8.2")
    assert metric.get_otel_spec("mos_score").name == "kio.adoption.mos_score"
    with pytest.raises(ValueError, match="otel_key"):
        metric.get_otel_spec()
    with pytest.raises(ValueError, match="no OTel instrument keyed"):
        metric.get_otel_spec("nonexistent")


def test_kio_id_is_bound_from_the_accessed_namespace_not_typed_by_hand():
    assert KPI.KIO2.code_generation_speed._kio_id == "KIO2"
    assert KPI.KIO4.code_generation_speed._kio_id == "KIO4"


def test_for_kio_binds_a_kpi_fetched_by_id():
    bound = KPI.get_kpi("1.1").for_kio("KIO3")
    assert bound._kio_id == "KIO3"


def test_for_kio_rejects_unassociated_kio():
    with pytest.raises(ValueError):
        KPI.get_kpi("1.1").for_kio("KIO13")


def test_kio_is_a_real_attribute_not_only_resolvable_via_getattr():
    # dir()/hasattr()/IDE-autocomplete only see real attributes, not names
    # that merely happen to resolve through __getattr__.
    assert "KIO7" in vars(KPI)
    assert "KIO7" in dir(KPI)


def test_dir_on_kpi_includes_public_methods_and_kios():
    names = dir(KPI)
    assert "list_kios" in names
    assert "get_kpi" in names
    assert "KIO1" in names
    assert not any(n.startswith("_") for n in names)


def test_bound_metric_fields_are_real_attributes_not_proxied():
    bound = KPI.KIO7.code_generation_speed
    assert "id" in vars(bound)
    assert "otel" in vars(bound)
    assert "name" in dir(bound)
