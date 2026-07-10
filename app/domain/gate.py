"""Path-assertion gate — чистая domain-функция (правило 6): фактический путь пачки vs
golden-разметка, membership по (branch, retry_cycles). Движок ассертов финализирован
(ROADMAP Заметки №2): pytest + этот membership, ноль новых зависимостей. Ассерт — только по
пути, не по тексту ответа: регрессия МАРШРУТИЗАЦИИ краснит гейт.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.domain.golden import GoldenRecord, path_allowed
from app.domain.path import PathTrace


def _path_label(branch: str, retry_cycles: int) -> str:
    return f"{branch} ↻{retry_cycles}"


@dataclass(frozen=True)
class GateRow:
    request_id: str
    expected: tuple[str, ...]  # допустимые пути из golden (для таблицы)
    actual: PathTrace | None  # None = заявка не прогнана (нет trace)
    ok: bool


@dataclass(frozen=True)
class GateReport:
    """Строки сравнения + вердикт. `passed` — единственный вход CI-гейта; `render` — таблица
    «ожидаемый vs фактический» для витрины. Сравнение — только по пути (branch, retry_cycles),
    не по тексту ответа."""

    rows: tuple[GateRow, ...]
    unexpected: tuple[str, ...]  # trace без golden-записи (пачка разошлась с разметкой)

    @property
    def regressions(self) -> tuple[GateRow, ...]:
        return tuple(r for r in self.rows if not r.ok)

    @property
    def passed(self) -> bool:
        return not self.regressions and not self.unexpected

    def render(self) -> str:
        width = max((len(r.request_id) for r in self.rows), default=0)
        lines = []
        for row in self.rows:
            mark = f"{'✓ ok' if row.ok else '✗ REGRESSION':<12}"
            expected = " | ".join(row.expected)
            actual = _path_label(row.actual.branch, row.actual.retry_cycles) if row.actual else "—"
            lines.append(f"{row.request_id:<{width}}  {mark}  ожид: {expected:<18}  факт: {actual}")
        if self.unexpected:
            lines.append(f"лишние в прогоне (нет в golden): {', '.join(self.unexpected)}")
        verdict = "PASS" if self.passed else f"FAIL — {len(self.regressions)} регрессий маршрута"
        return "\n".join(lines) + f"\n{'─' * 64}\n{verdict}"


def _expected(record: GoldenRecord) -> tuple[str, ...]:
    return tuple(_path_label(p.branch, p.retry_cycles) for p in record.allowed_paths)


def _row(rid: str, record: GoldenRecord, trace: PathTrace | None) -> GateRow:
    return GateRow(
        request_id=rid,
        expected=_expected(record),
        actual=trace,
        ok=trace is not None and path_allowed(trace, record),
    )


def build_gate_report(traces: Mapping[str, PathTrace], golden: list[GoldenRecord]) -> GateReport:
    """Membership каждого пройденного пути в golden allowed_paths. Строки — по golden-записям
    (source of truth ожидаемого); trace без записи — в `unexpected`."""
    by_id = {g.request_id: g for g in golden}
    rows = tuple(_row(rid, record, traces.get(rid)) for rid, record in sorted(by_id.items()))
    unexpected = tuple(sorted(set(traces) - set(by_id)))
    return GateReport(rows=rows, unexpected=unexpected)
