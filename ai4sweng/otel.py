"""Optional OpenTelemetry recording backend.

`opentelemetry-api` is only imported lazily, the first time a metric is
actually recorded. `pip install ai4sweng` alone (without the `otel` extra)
works fine for reading metadata; `.record()` raises a clear ImportError
pointing at `pip install ai4sweng[otel]` if the dependency is missing.

You should not need to import this module directly — use
`KPI.KIOx.<metric>.record(...)` instead (see
`ai4sweng.kpi._BoundKPIMetric.record`, which calls `emit()` below).
"""

_meter = None
_instruments = {}


def _get_meter():
    """Return the process-wide OTel Meter for "ai4sweng", creating it on first use.

    Deferred like this so importing `ai4sweng` never requires
    `opentelemetry-api` to be installed — only calling `.record()` does.

    Raises:
        ImportError: `opentelemetry-api` isn't installed.
    """
    global _meter
    if _meter is None:
        try:
            from opentelemetry import metrics as otel_metrics
        except ImportError as exc:
            raise ImportError(
                "Recording KPI metrics via OpenTelemetry requires the 'otel' extra: "
                "pip install ai4sweng[otel]"
            ) from exc
        _meter = otel_metrics.get_meter("ai4sweng")
    return _meter


def _get_instrument(spec):
    """Get (or lazily create and cache) the OTel instrument described by `spec`.

    Instruments are cached by (name, instrument kind, unit) so recording the
    same KPI repeatedly reuses one instrument instead of re-registering it
    with the SDK on every call.

    Args:
        spec: An `ai4sweng.kpi.OTelSpec` describing what to create.

    Raises:
        ImportError: `opentelemetry-api` is missing, or too old to support
            `spec.instrument` (e.g. synchronous Gauge needs >=1.23).
    """
    key = (spec.name, spec.instrument, spec.unit)
    instrument = _instruments.get(key)
    if instrument is not None:
        return instrument

    meter = _get_meter()
    factories = {
        "Counter": meter.create_counter,
        "UpDownCounter": meter.create_up_down_counter,
        "Histogram": meter.create_histogram,
        "Gauge": getattr(meter, "create_gauge", None),
    }
    factory = factories.get(spec.instrument)
    if factory is None:
        raise ImportError(
            f"Instrument kind {spec.instrument!r} requires opentelemetry-api>=1.23 "
            "(synchronous Gauge support). Upgrade with: "
            "pip install -U 'opentelemetry-api>=1.23'"
        )
    instrument = factory(name=spec.name, unit=spec.unit, description=spec.name)
    _instruments[key] = instrument
    return instrument


def emit(spec, kio_id: str, value, attributes: dict) -> dict:
    """Validate required attributes, then record `value` on the correctly
    typed OTel instrument described by `spec`. `kio.id` is injected
    automatically from the KIO namespace the metric was accessed through —
    it is never taken from `attributes`, so it cannot be mistyped or omitted.

    This is the implementation behind `_BoundKPIMetric.record()`; call that
    instead of this function directly (it already resolves which `OTelSpec`
    to use via `KPIMetric.get_otel_spec()`).

    Args:
        spec: The `ai4sweng.kpi.OTelSpec` to record against.
        kio_id: Which KIO this data point is attributed to.
        value: The measurement to record.
        attributes: Extra attributes from the caller (must cover every key
            in `spec.caller_attributes`).

    Returns:
        The full attribute dict actually recorded, including "kio.id".

    Raises:
        ValueError: a required attribute is missing.

    Example:
        >>> from ai4sweng import KPI, otel
        >>> spec = KPI.get_kpi("1.1").get_otel_spec()
        >>> otel.emit(spec, "KIO7", 95.0, {"source": "ci"})  # doctest: +SKIP
        {'kio.id': 'KIO7', 'source': 'ci'}
    """
    missing = [key for key in spec.caller_attributes if key not in attributes]
    if missing:
        raise ValueError(
            f"Missing required attribute(s) for {spec.name!r}: {', '.join(missing)}. "
            f"Required from caller: {spec.caller_attributes}"
        )

    full_attributes = {"kio.id": kio_id, **attributes}
    instrument = _get_instrument(spec)

    if spec.instrument in ("Counter", "UpDownCounter"):
        instrument.add(value, attributes=full_attributes)
    elif spec.instrument == "Histogram":
        instrument.record(value, attributes=full_attributes)
    elif spec.instrument == "Gauge":
        instrument.set(value, attributes=full_attributes)
    else:
        raise ValueError(f"Unsupported instrument kind: {spec.instrument!r}")

    return full_attributes


def reset_cache():
    """Testing hook: drop the cached meter/instruments.

    Not needed in normal use. Useful in tests that install a fresh
    `MeterProvider` (e.g. with an `InMemoryMetricReader`) and need
    `ai4sweng` to pick it up instead of reusing an already-cached meter.

    Example:
        >>> from ai4sweng import otel
        >>> otel.reset_cache()
    """
    global _meter
    _meter = None
    _instruments.clear()
