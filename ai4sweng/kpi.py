"""KPI <-> KIO metric catalog and OpenTelemetry instrumentation contract.

The public entry point is the `KPI` singleton exported from `ai4sweng`:

    from ai4sweng import KPI

    metric = KPI.KIO7.code_generation_speed    # KPI metadata, bound to KIO7
    metric.record(95.0, source="ci-pipeline")  # emit a correctly labeled OTel measurement

`KPI.KIO7` and `.code_generation_speed` are built dynamically from
metrics.json the first time the package is used (see `_KPIInterface._load`
and `_KIONamespace.__init__`), but are set as *real* instance attributes —
not resolved through `__getattr__` magic — specifically so that `dir(KPI)`,
`hasattr(...)`, and IDE/IPython autocomplete all see them. `__getattr__` on
`_KPIInterface` only exists as a fallback that gives a helpful error message
for KIOs that don't exist.

Static type checkers (Pylance, mypy, PyCharm) still can't see attributes
that are only set at runtime, even real ones — they read source, they don't
execute it. For that, this package ships a generated stub,
`ai4sweng/__init__.pyi` (see `scripts/gen_stubs.py`), which is what actually
makes `KPI.KIO7.<Tab>` autocomplete in an editor. Re-run that script after
editing metrics.json.

For a fuller description of any object here, use Python's built-in help:

    >>> from ai4sweng import KPI
    >>> help(KPI.list_kios)         # doctest: +SKIP
    >>> help(KPI.KIO7.code_generation_speed.record)  # doctest: +SKIP
"""

import json
import re
import unicodedata
from pathlib import Path

from . import otel as _otel_backend

_VALID_INSTRUMENTS = {"Counter", "UpDownCounter", "Histogram", "Gauge"}


def _slugify(name: str) -> str:
    """Derive a valid Python identifier from a KPI display name.

    This is only used as a fallback when a metrics.json entry has no
    explicit "attr" field. It strips accents, lowercases, and collapses
    any run of non-alphanumeric characters into a single underscore.

    Example:
        >>> _slugify("Code generation speed")
        'code_generation_speed'
    """
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    return slug or "kpi"


class OTelSpec:
    """The OpenTelemetry instrumentation contract for one KPI metric: not
    just a name, but the instrument kind, unit and attribute keys required
    to emit it correctly. `kio.id` is always auto-injected by the package
    (see `_BoundKPIMetric.record`) and is never a caller-supplied attribute.

    Most KPIs have exactly one OTelSpec (`KPIMetric.otel_specs` has one
    element, and the `KPIMetric.otel` convenience property is that element
    directly). A few KPIs are realized as more than one real OTel metric —
    e.g. KPI 8.2 ("Active usage & satisfaction") is actually two separate
    histograms in the real telemetry producer, `kio.adoption.usage_pct` and
    `kio.adoption.mos_score`. For those, each OTelSpec carries a distinct
    `key`, and callers must pick one via `.record(value, otel_key=..., ...)`.

    Attributes:
        key: Disambiguates this spec among a KPI's other OTelSpecs when
            there is more than one (e.g. "usage_pct"). None when this is a
            KPI's only spec.
        name: Canonical OTel metric name, e.g. "kio.codegen.duration_minutes".
        instrument: One of "Counter", "UpDownCounter", "Histogram", "Gauge".
        unit: Raw OTel/UCUM-style unit of the *instrumented* value (e.g. "s",
            "1"). Not the same as `KPIMetric.unit`, which is the business/
            reporting unit from the KPI table (e.g. "% of baseline duration").
        caller_attributes: Attribute keys the caller must pass to `.record()`,
            not counting the auto-injected "kio.id".
        required_attributes: `caller_attributes` plus the auto-injected
            "kio.id" — i.e. the full attribute set a recorded data point
            will carry.

    Example:
        >>> from ai4sweng import KPI
        >>> spec = KPI.KIO7.code_generation_speed.otel
        >>> spec.instrument
        'Histogram'
        >>> spec.required_attributes
        ['kio.id', 'source', 'llm', 'task_type']
    """

    AUTO_ATTRIBUTES = ("kio.id",)

    def __init__(self, data: dict, metric_attr: str):
        """Parse one entry of a metrics.json "otel" list into an OTelSpec.

        Raises:
            ValueError: `data["instrument"]` is missing or not one of
                Counter/UpDownCounter/Histogram/Gauge.
        """
        self.key = data.get("key")
        default_name = f"ai4sweng.kpi.{metric_attr}" + (f".{self.key}" if self.key else "")
        self.name = data.get("name") or default_name
        instrument = data.get("instrument")
        if instrument not in _VALID_INSTRUMENTS:
            raise ValueError(
                f"Invalid OTel instrument {instrument!r} for {metric_attr!r}. "
                f"Must be one of: {sorted(_VALID_INSTRUMENTS)}"
            )
        self.instrument = instrument
        self.unit = data.get("unit", "1")
        self.caller_attributes = list(data.get("required_attributes", []))
        self.required_attributes = list(self.AUTO_ATTRIBUTES) + self.caller_attributes

    def __repr__(self):
        """Debug representation showing every field, e.g. in a REPL or logs."""
        key_part = f"key={self.key!r}, " if self.key else ""
        return (
            f"OTelSpec({key_part}name={self.name!r}, instrument={self.instrument!r}, "
            f"unit={self.unit!r}, required_attributes={self.required_attributes!r})"
        )


class KPIMetric:
    """A single KPI definition, as tracked by one or more KIO modules.

    Read-only metadata about one row of the KPI catalog: what it measures
    (`definition`), its baseline/target framing for reporting, and its
    OpenTelemetry instrumentation contract (`otel`). Fetched via
    `KPI.KIOx.<attr>` (bound to a specific KIO, see `_BoundKPIMetric`),
    `KPI.get_kpi(kpi_id)` (unbound), or `KPI.list_kpis()`.

    Attributes:
        id: The KPI's catalog id, e.g. "1.1".
        name: Short display name, e.g. "Code generation speed".
        attr: The Python attribute name it's exposed under, e.g.
            `KPI.KIO7.code_generation_speed`.
        definition: One-sentence description of what is measured.
        unit: Business/reporting unit, e.g. "% of baseline duration".
        baseline: Baseline value/range for this KPI.
        target: Target value/range for this KPI.
        kios: The KIOs this KPI is associated with, e.g. ["KIO2", "KIO3", ...].
        otel_specs: This KPI's `OTelSpec`s, in metrics.json order. Empty if
            metrics.json defines no "otel" block for it yet.
        otel: Convenience for the common case — `otel_specs[0]` when there's
            exactly one, otherwise None (including when there are zero *or*
            more than one; use `otel_specs` or `get_otel_spec()` for those).

    Example:
        >>> from ai4sweng import KPI
        >>> metric = KPI.get_kpi("1.1")
        >>> metric.name
        'Code generation speed'
        >>> metric.kios
        ['KIO2', 'KIO3', 'KIO4', 'KIO7']
    """

    def __init__(self, data: dict):
        """Build a KPIMetric from one JSON object in metrics.json's "kpis" list.

        Raises:
            ValueError: `data["otel"]` is present but isn't a list.
        """
        self.id = data["id"]
        self.name = data["name"]
        self.attr = data.get("attr") or _slugify(data["name"])
        self.definition = data.get("definition", "")
        self.unit = data.get("unit", "")
        self.baseline = data.get("baseline", "")
        self.target = data.get("target", "")
        self.kios = list(data.get("kios", []))

        otel_data = data.get("otel")
        if otel_data is None:
            self.otel_specs = []
        elif isinstance(otel_data, list):
            self.otel_specs = [OTelSpec(entry, self.attr) for entry in otel_data]
        else:
            raise ValueError(
                f"KPI {self.id!r}: 'otel' must be a list of instrument specs "
                f"(even when there's only one), got {type(otel_data).__name__}."
            )
        self.otel = self.otel_specs[0] if len(self.otel_specs) == 1 else None

    def get_otel_spec(self, otel_key: str = None) -> OTelSpec:
        """Resolve which of this KPI's `OTelSpec`s a `.record()` call should use.

        `otel_key` is optional when there's exactly one spec (the common
        case) and required when there's more than one — see `OTelSpec.key`.

        Raises:
            ValueError: this KPI has no OTelSpec at all, `otel_key` was
                required but omitted, or it doesn't match any spec's `.key`.

        Example:
            >>> from ai4sweng import KPI
            >>> KPI.get_kpi("1.1").get_otel_spec().name
            'kio.codegen.duration_minutes'
            >>> KPI.get_kpi("8.2").get_otel_spec("mos_score").name
            'kio.adoption.mos_score'
        """
        if not self.otel_specs:
            raise ValueError(f"KPI {self.id!r} ({self.name!r}) has no 'otel' spec in metrics.json.")
        if len(self.otel_specs) == 1:
            return self.otel_specs[0]
        available = [spec.key for spec in self.otel_specs]
        if otel_key is None:
            raise ValueError(
                f"KPI {self.id!r} has multiple OTel instruments: {available}. "
                f"Pass otel_key=<one of these> to .record()."
            )
        for spec in self.otel_specs:
            if spec.key == otel_key:
                return spec
        raise ValueError(f"KPI {self.id!r} has no OTel instrument keyed {otel_key!r}. Available: {available}")

    def for_kio(self, kio_id: str) -> "_BoundKPIMetric":
        """Bind this KPI to one of its associated KIOs.

        Needed to `.record()` a KPI you fetched via `get_kpi()`/`list_kpis()`,
        since (unlike `KPI.KIOx.<attr>`) those aren't already tied to a
        single KIO.

        Args:
            kio_id: A KIO this KPI is associated with, e.g. "KIO3".

        Raises:
            ValueError: `kio_id` is not in `self.kios`.

        Example:
            >>> from ai4sweng import KPI
            >>> bound = KPI.get_kpi("1.1").for_kio("KIO3")
            >>> bound.record(95.0, source="ci-pipeline")  # doctest: +SKIP
        """
        if kio_id not in self.kios:
            raise ValueError(f"KPI {self.id!r} is not associated with {kio_id!r}. Associated KIOs: {self.kios}")
        return _BoundKPIMetric(self, kio_id)

    def __repr__(self):
        """Unambiguous debug representation, e.g. in a REPL or logs."""
        return (
            f"KPIMetric(id={self.id!r}, name={self.name!r}, unit={self.unit!r}, "
            f"baseline={self.baseline!r}, target={self.target!r}, kios={self.kios!r})"
        )

    def __str__(self):
        """Human-readable one-liner, used by e.g. `print(metric)`.

        Example:
            >>> from ai4sweng import KPI
            >>> print(KPI.get_kpi("1.1"))
            [1.1] Code generation speed: 100% (~100-120 min) -> ≤ 70% (~30% reduction) (% of baseline duration)
        """
        return f"[{self.id}] {self.name}: {self.baseline} -> {self.target} ({self.unit})"

    def as_dict(self) -> dict:
        """Export the business-facing metadata (not the OTel contract) as a plain dict.

        Useful for JSON-serializing a KPI, e.g. to expose it over an API.

        Example:
            >>> from ai4sweng import KPI
            >>> KPI.get_kpi("8.3").as_dict()["target"]
            '≥ 1 validated target'
        """
        return {
            "id": self.id,
            "name": self.name,
            "definition": self.definition,
            "unit": self.unit,
            "baseline": self.baseline,
            "target": self.target,
            "kios": list(self.kios),
        }


class _BoundKPIMetric:
    """A KPIMetric as seen through one specific KIO namespace.

    This is what `KPI.KIOx.<attr>` actually returns. Every field of the
    underlying `KPIMetric` (`.id`, `.name`, `.definition`, `.otel`, ...) is
    copied onto this object as a real attribute in `__init__` — deliberately
    *not* proxied through `__getattr__` — so that `dir(...)`, IPython/REPL
    completion, and static type checkers can all see them. On top of that,
    it adds `.record()`, which is only offered here (not on `KPIMetric`
    itself) because this object already knows which KIO it was accessed
    through. That's exactly the `kio.id` value it will attach when
    recording, so it never has to be typed by hand at the call site.

    Example:
        >>> from ai4sweng import KPI
        >>> bound = KPI.KIO7.code_generation_speed
        >>> bound.id
        '1.1'
        >>> bound.record(95.0, source="ci-pipeline")  # doctest: +SKIP
    """

    def __init__(self, metric: KPIMetric, kio_id: str):
        """Copy `metric`'s fields onto this object and bind it to `kio_id`."""
        self._metric = metric
        self._kio_id = kio_id
        self.id = metric.id
        self.name = metric.name
        self.attr = metric.attr
        self.definition = metric.definition
        self.unit = metric.unit
        self.baseline = metric.baseline
        self.target = metric.target
        self.kios = metric.kios
        self.otel = metric.otel
        self.otel_specs = metric.otel_specs

    def __repr__(self):
        """Delegate to the wrapped KPIMetric's repr."""
        return repr(self._metric)

    def __str__(self):
        """Delegate to the wrapped KPIMetric's str, used by e.g. `print(KPI.KIO7.code_generation_speed)`."""
        return str(self._metric)

    def as_dict(self) -> dict:
        """Export the business-facing metadata as a plain dict. See `KPIMetric.as_dict`."""
        return self._metric.as_dict()

    def record(self, value, otel_key: str = None, **attributes) -> dict:
        """Record `value` on the correctly-typed OTel instrument for this KPI.

        Requires `pip install ai4sweng[otel]`. `kio.id` is attached
        automatically (the KIO this object was accessed through); any other
        key listed in the resolved spec's `.required_attributes` must be
        passed as a keyword argument here, or this raises ValueError.

        Args:
            value: The measurement. Its shape follows the instrument kind:
                a duration/amount for Histogram, a delta for Counter/
                UpDownCounter, or the current reading for Gauge.
            otel_key: Only needed for the few KPIs realized as more than one
                OTel metric (see `OTelSpec.key`, e.g. KPI 8.2's "usage_pct"
                vs "mos_score"). Omit it for the common single-instrument case.
            **attributes: Extra OTel attributes required by this KPI's
                `otel.required_attributes` (e.g. `source=...`).

        Returns:
            The full attribute set actually recorded (including the
            auto-injected "kio.id"), handy for logging/tests.

        Raises:
            ValueError: a required attribute is missing, this KPI has no
                `otel` block in metrics.json yet, or (for a multi-instrument
                KPI) `otel_key` was omitted or didn't match any spec.
            ImportError: `opentelemetry-api` isn't installed, or the
                instrument kind needs a newer version (e.g. Gauge).

        Example:
            >>> from ai4sweng import KPI
            >>> KPI.KIO7.code_generation_speed.record(95.0, source="ci-pipeline")  # doctest: +SKIP
            {'kio.id': 'KIO7', 'source': 'ci-pipeline'}
            >>> KPI.KIO13.active_usage_satisfaction.record(62.0, otel_key="usage_pct", source="svc")  # doctest: +SKIP
        """
        spec = self._metric.get_otel_spec(otel_key)
        return _otel_backend.emit(spec, self._kio_id, value, attributes)


class _KIONamespace:
    """Attribute namespace exposing the KPI metrics tracked by one KIO module.

    This is what `KPI.KIO7` itself evaluates to; `KPI.KIO7.code_generation_speed`
    is then a plain, real attribute lookup on this object (not `__getattr__`
    magic — see `_BoundKPIMetric`). Built once per KIO when the package
    loads (or `KPI.reload()` runs), from every KPI in metrics.json whose
    `kios` list includes this KIO.

    Example:
        >>> from ai4sweng import KPI
        >>> "code_generation_speed" in dir(KPI.KIO7)
        True
        >>> for m in KPI.KIO8:
        ...     pass  # iterate every metric KIO8 tracks
    """

    def __init__(self, kio_name: str, metrics: list):
        """Bind each KPIMetric in `metrics` to `kio_name`, as a `_BoundKPIMetric` attribute."""
        self._kio_name = kio_name
        self._bound = {m.attr: _BoundKPIMetric(m, kio_name) for m in metrics}
        for attr, bound in self._bound.items():
            setattr(self, attr, bound)

    def __dir__(self):
        """List this KIO's metric attribute names, e.g. for tab-completion in a REPL."""
        return list(self._bound.keys())

    def __iter__(self):
        """Iterate every metric this KIO tracks, as bound `_BoundKPIMetric` objects.

        Example:
            >>> from ai4sweng import KPI
            >>> names = [m.attr for m in KPI.KIO7]
            >>> "code_generation_speed" in names
            True
        """
        return iter(self._bound.values())

    def __len__(self):
        """Number of metrics this KIO tracks (0 if none are assigned yet).

        Example:
            >>> from ai4sweng import KPI
            >>> len(KPI.KIO5)
            0
        """
        return len(self._bound)

    def __repr__(self):
        """Debug representation listing this KIO's metric attribute names."""
        return f"<{self._kio_name}: {', '.join(self._bound.keys()) or 'no metrics assigned'}>"


class _KPIInterface:
    """Singleton entry point: `KPI.KIO1.<metric_name>` -> `_BoundKPIMetric`.

    Instantiated once at the bottom of this module and re-exported as `KPI`
    from `ai4sweng/__init__.py`, so `from ai4sweng import KPI` always gives
    you the same object. `KPI.KIO1`, `KPI.KIO2`, etc. are set as real
    instance attributes by `_load()` (so `dir(KPI)`, `hasattr(...)`, and
    REPL/IPython completion see them); `__getattr__` below only runs as a
    fallback, for names that turn out not to be a declared KIO, to give a
    helpful error instead of a bare AttributeError.

    Example:
        >>> from ai4sweng import KPI
        >>> "KIO7" in KPI.list_kios()
        True
        >>> KPI.KIO7.code_generation_speed.id
        '1.1'
    """

    _instance = None

    def __new__(cls):
        """Return the single shared instance, loading metrics.json on first use."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """Parse metrics.json, index KPIs by KIO, and set `KPI.KIOx` as real attributes.

        Called once on first use, and again by `reload()` (which also drops
        any `KIOx` attribute from a previous load that no longer exists).
        """
        metrics_path = Path(__file__).parent / "metrics.json"
        with open(metrics_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        kpis = [KPIMetric(entry) for entry in raw.get("kpis", [])]

        by_kio = {kio: [] for kio in raw.get("kios", [])}
        for metric in kpis:
            for kio in metric.kios:
                by_kio.setdefault(kio, []).append(metric)

        kio_namespaces = {kio: _KIONamespace(kio, metrics) for kio, metrics in by_kio.items()}

        for stale_kio in set(self.__dict__.get("_kio_namespaces", {})) - set(kio_namespaces):
            self.__dict__.pop(stale_kio, None)

        self.__dict__["_kpis"] = kpis
        self.__dict__["_by_kio"] = by_kio
        self.__dict__["_kio_namespaces"] = kio_namespaces
        self.__dict__.update(kio_namespaces)  # real attributes: KPI.KIO1, KPI.KIO2, ...

    def reload(self):
        """Reload metrics.json from disk, e.g. right after editing it.

        No process restart needed. Fetch `KPI.KIOx.<attr>` again after
        calling this to see the updated data.

        Example:
            >>> from ai4sweng import KPI
            >>> KPI.reload()  # picks up any metrics.json edits since import
        """
        self._load()

    def __getattr__(self, name: str):
        """Fallback for names that aren't real attributes (declared KIOs are —
        see `_load`), e.g. a typo like `KPI.KI07` or a KIO removed since the
        last `reload()`. Raises AttributeError listing the KIOs that do exist.
        """
        if not name.startswith("_"):
            namespaces = self.__dict__.get("_kio_namespaces", {})
            if name in namespaces:
                return namespaces[name]
        raise AttributeError(
            f"'KPI' object has no attribute {name!r}. Available KIOs: {', '.join(self.list_kios())}"
        )

    def __dir__(self):
        """List every declared KIO plus the public methods, e.g. for tab-completion in a REPL."""
        public_methods = (name for name in vars(type(self)) if not name.startswith("_"))
        return sorted(set(public_methods) | set(self._kio_namespaces.keys()))

    def list_kios(self) -> list:
        """List every declared KIO name, sorted numerically (KIO1, KIO2, ..., KIO13, ...).

        Includes KIOs with zero metrics assigned yet (declared in the `kios`
        array at the top of metrics.json).

        Example:
            >>> from ai4sweng import KPI
            >>> kios = KPI.list_kios()
            >>> "KIO1" in kios and "KIO13" in kios
            True
        """
        return sorted(self._kio_namespaces.keys(), key=lambda k: int(re.sub(r"\D", "", k) or 0))

    def list_kpis(self) -> list:
        """List every KPI in the catalog, as unbound `KPIMetric` objects.

        Example:
            >>> from ai4sweng import KPI
            >>> ids = [k.id for k in KPI.list_kpis()]
            >>> "1.1" in ids
            True
        """
        return list(self._kpis)

    def get_kio_metrics(self, kio_name: str) -> dict:
        """Get every metric tracked by `kio_name`, keyed by attribute name.

        The values are bound `_BoundKPIMetric` objects (same as
        `KPI.KIOx.<attr>`), so you can `.record()` on them directly.

        Args:
            kio_name: e.g. "KIO8".

        Raises:
            KeyError: `kio_name` isn't declared in metrics.json.

        Example:
            >>> from ai4sweng import KPI
            >>> metrics = KPI.get_kio_metrics("KIO8")
            >>> "lifecycle_energy_reduction" in metrics
            True
        """
        if kio_name not in self._kio_namespaces:
            raise KeyError(f"KIO {kio_name!r} not found. Available: {self.list_kios()}")
        return dict(self._kio_namespaces[kio_name]._bound)

    def get_kpi(self, kpi_id: str) -> KPIMetric:
        """Fetch a single KPI by its catalog id (e.g. "9.2"), unbound to any KIO.

        Use `.for_kio(kio_id)` on the result if you need to `.record()` it —
        a KPI fetched by id alone isn't tied to one specific KIO the way
        `KPI.KIOx.<attr>` is.

        Raises:
            KeyError: no KPI with this id exists.

        Example:
            >>> from ai4sweng import KPI
            >>> KPI.get_kpi("9.2").name
            'Technical debt reduction'
        """
        for metric in self._kpis:
            if metric.id == kpi_id:
                return metric
        raise KeyError(f"KPI {kpi_id!r} not found")


KPI = _KPIInterface()
