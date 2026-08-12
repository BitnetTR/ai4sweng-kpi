import json
import re
import unicodedata
from pathlib import Path

from . import otel as _otel_backend

_VALID_INSTRUMENTS = {"Counter", "UpDownCounter", "Histogram", "Gauge"}


def _slugify(name: str) -> str:
    """Fallback: turn a KPI display name into a valid Python identifier."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    return slug or "kpi"


class OTelSpec:
    """The OpenTelemetry instrumentation contract for one KPI: not just a
    name, but the instrument kind, unit and attribute keys required to emit
    it correctly. `kio.id` is always auto-injected by the package (see
    `_BoundKPIMetric.record`) and is never a caller-supplied attribute.
    """

    AUTO_ATTRIBUTES = ("kio.id",)

    def __init__(self, data: dict, metric_attr: str):
        self.name = data.get("name") or f"ai4sweng.kpi.{metric_attr}"
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
        return (
            f"OTelSpec(name={self.name!r}, instrument={self.instrument!r}, "
            f"unit={self.unit!r}, required_attributes={self.required_attributes!r})"
        )


class KPIMetric:
    """A single KPI definition, as tracked by one or more KIO modules."""

    def __init__(self, data: dict):
        self.id = data["id"]
        self.name = data["name"]
        self.attr = data.get("attr") or _slugify(data["name"])
        self.definition = data.get("definition", "")
        self.unit = data.get("unit", "")
        self.baseline = data.get("baseline", "")
        self.target = data.get("target", "")
        self.kios = list(data.get("kios", []))
        otel_data = data.get("otel")
        self.otel = OTelSpec(otel_data, self.attr) if otel_data else None

    def for_kio(self, kio_id: str) -> "_BoundKPIMetric":
        """Bind this KPI to one of its associated KIOs, so it can be `.record()`-ed
        with `kio.id` auto-attached. Use this when you got the metric via
        `get_kpi()`/`list_kpis()` instead of `KPI.KIOx.<attr>`."""
        if kio_id not in self.kios:
            raise ValueError(f"KPI {self.id!r} is not associated with {kio_id!r}. Associated KIOs: {self.kios}")
        return _BoundKPIMetric(self, kio_id)

    def __repr__(self):
        return (
            f"KPIMetric(id={self.id!r}, name={self.name!r}, unit={self.unit!r}, "
            f"baseline={self.baseline!r}, target={self.target!r}, kios={self.kios!r})"
        )

    def __str__(self):
        return f"[{self.id}] {self.name}: {self.baseline} -> {self.target} ({self.unit})"

    def as_dict(self) -> dict:
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
    """A KPIMetric as seen through one specific KIO namespace. Carries the
    `kio.id` context needed to record a correctly labeled OTel data point,
    so `kio.id` never has to be typed by hand at the call site.
    """

    def __init__(self, metric: KPIMetric, kio_id: str):
        self._metric = metric
        self._kio_id = kio_id

    def __getattr__(self, name):
        return getattr(self._metric, name)

    def __repr__(self):
        return repr(self._metric)

    def __str__(self):
        return str(self._metric)

    def record(self, value, **attributes) -> dict:
        """Record `value` on the correctly-typed OTel instrument for this KPI.
        Requires `pip install ai4sweng[otel]`. Raises ValueError if a required
        attribute (per `metric.otel.required_attributes`) is missing.
        Returns the full attribute set actually recorded (for logging/tests).
        """
        return _otel_backend.emit(self._metric, self._kio_id, value, attributes)


class _KIONamespace:
    """Attribute namespace exposing the KPI metrics tracked by one KIO module."""

    def __init__(self, kio_name: str, metrics: list):
        self._kio_name = kio_name
        self._metrics = {m.attr: m for m in metrics}
        for attr, metric in self._metrics.items():
            setattr(self, attr, _BoundKPIMetric(metric, kio_name))

    def __dir__(self):
        return list(self._metrics.keys())

    def __iter__(self):
        return (_BoundKPIMetric(m, self._kio_name) for m in self._metrics.values())

    def __len__(self):
        return len(self._metrics)

    def __repr__(self):
        return f"<{self._kio_name}: {', '.join(self._metrics.keys()) or 'no metrics assigned'}>"


class _KPIInterface:
    """Singleton entry point: KPI.KIO1.<metric_name> -> _BoundKPIMetric."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        metrics_path = Path(__file__).parent / "metrics.json"
        with open(metrics_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        kpis = [KPIMetric(entry) for entry in raw.get("kpis", [])]

        by_kio = {kio: [] for kio in raw.get("kios", [])}
        for metric in kpis:
            for kio in metric.kios:
                by_kio.setdefault(kio, []).append(metric)

        self.__dict__["_kpis"] = kpis
        self.__dict__["_by_kio"] = by_kio
        self.__dict__["_kio_namespaces"] = {
            kio: _KIONamespace(kio, metrics) for kio, metrics in by_kio.items()
        }

    def reload(self):
        """Reload metrics.json from disk (e.g. after editing it)."""
        self._load()

    def __getattr__(self, name: str):
        if not name.startswith("_"):
            namespaces = self.__dict__.get("_kio_namespaces", {})
            if name in namespaces:
                return namespaces[name]
        raise AttributeError(
            f"'KPI' object has no attribute {name!r}. Available KIOs: {', '.join(self.list_kios())}"
        )

    def __dir__(self):
        return list(self._kio_namespaces.keys())

    def list_kios(self) -> list:
        return sorted(self._kio_namespaces.keys(), key=lambda k: int(re.sub(r"\D", "", k) or 0))

    def list_kpis(self) -> list:
        return list(self._kpis)

    def get_kio_metrics(self, kio_name: str) -> dict:
        if kio_name not in self._by_kio:
            raise KeyError(f"KIO {kio_name!r} not found. Available: {self.list_kios()}")
        return {m.attr: _BoundKPIMetric(m, kio_name) for m in self._by_kio[kio_name]}

    def get_kpi(self, kpi_id: str) -> KPIMetric:
        for metric in self._kpis:
            if metric.id == kpi_id:
                return metric
        raise KeyError(f"KPI {kpi_id!r} not found")


KPI = _KPIInterface()
