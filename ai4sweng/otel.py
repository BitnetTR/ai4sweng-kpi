"""Optional OpenTelemetry recording backend.

`opentelemetry-api` is only imported lazily, the first time a metric is
actually recorded. `pip install ai4sweng` alone (without the `otel` extra)
works fine for reading metadata; `.record()` raises a clear ImportError
pointing at `pip install ai4sweng[otel]` if the dependency is missing.
"""

_meter = None
_instruments = {}


def _get_meter():
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


def emit(metric, kio_id: str, value, attributes: dict) -> dict:
    """Validate required attributes, then record `value` on the correctly
    typed OTel instrument for `metric`. `kio.id` is injected automatically
    from the KIO namespace the metric was accessed through — it is never
    taken from `attributes`, so it cannot be mistyped or omitted.
    """
    spec = metric.otel
    if spec is None:
        raise ValueError(
            f"KPI {metric.id!r} ({metric.name!r}) has no 'otel' spec in metrics.json; "
            "add one before calling .record()."
        )

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
    """Testing hook: drop cached meter/instruments so a fresh SDK setup is picked up."""
    global _meter
    _meter = None
    _instruments.clear()
