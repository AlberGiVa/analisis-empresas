"""Values that may be unavailable, together with the reason. Nothing is ever filled in silently."""

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    """Why a value is (or is not) available."""

    OK = "ok"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    DIVISION_BY_ZERO = "division_by_zero"
    NOT_MEANINGFUL = "not_meaningful"
    STALE = "stale"
    INSUFFICIENT_PEERS = "insufficient_peers"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]


_STATUS_LABELS = {
    Status.OK: "Con dato",
    Status.MISSING: "Sin dato",
    Status.NOT_APPLICABLE: "No aplica",
    Status.DIVISION_BY_ZERO: "División por cero",
    Status.NOT_MEANINGFUL: "No significativo",
    Status.STALE: "Dato desactualizado",
    Status.INSUFFICIENT_PEERS: "Sin comparables suficientes",
}


@dataclass(frozen=True)
class Figure:
    """A labelled number, or the status and detail that explain why it is unavailable.

    ``detail`` explains an unavailable figure; for an available one it may record its source.
    """

    label: str
    value: float | None
    status: Status = Status.OK
    detail: str | None = None

    def __post_init__(self) -> None:
        if (self.value is None) == (self.status is Status.OK):
            raise ValueError("A figure has a value if and only if its status is OK")

    @classmethod
    def unavailable(cls, label: str, status: Status, detail: str) -> Figure:
        return cls(label, None, status, detail)

    @property
    def ok(self) -> bool:
        return self.status is Status.OK

    def number(self) -> float:
        """The value of an available figure (call only after checking ``ok``)."""
        if self.value is None:
            raise ValueError(f"{self.label} no tiene valor: {self.detail}")
        return self.value

    def explanation(self) -> str:
        """Human-readable reason why the figure is unavailable."""
        return f"{self.label}: {self.detail}" if self.detail else self.label
