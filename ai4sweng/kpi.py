import json
import re
import unicodedata
from pathlib import Path


def _slugify(name: str) -> str:
    """Fallback: turn a KPI display name into a valid Python identifier."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_name).strip("_").lower()
    return slug or "kpi"


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


class _KIONamespace:
    """Attribute namespace exposing the KPI metrics tracked by one KIO module."""

    def __init__(self, kio_name: str, metrics: list):
        self._kio_name = kio_name
        self._metrics = {m.attr: m for m in metrics}
        for attr, metric in self._metrics.items():
            setattr(self, attr, metric)

    def __dir__(self):
        return list(self._metrics.keys())

    def __iter__(self):
        return iter(self._metrics.values())

    def __len__(self):
        return len(self._metrics)

    def __repr__(self):
        return f"<{self._kio_name}: {', '.join(self._metrics.keys()) or 'no metrics assigned'}>"


class _KPIInterface:
    """Singleton entry point: KPI.KIO1.<metric_name> -> KPIMetric."""

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
        return {m.attr: m for m in self._by_kio[kio_name]}

    def get_kpi(self, kpi_id: str) -> KPIMetric:
        for metric in self._kpis:
            if metric.id == kpi_id:
                return metric
        raise KeyError(f"KPI {kpi_id!r} not found")


KPI = _KPIInterface()
