"""Тонкий транспорт: path-assertion gate. Прогоняет пачку через граф (replay, $0), печатает
таблицу «ожидаемый vs фактический путь» и выходит с ненулевым кодом при регрессии маршрута.
Пишет RunRecord JSONL-артефакт прогона (контракт №3 — его читают потребители iter 4/5/7).

Набор кассет — AW_CASSETTE_SET; `--ids a,b,c` сужает пачку (демо сломанного subset). Гейт
краснеет ИЗ-ЗА СМЕНЫ МАРШРУТА: replay-miss — громкая ошибка (не тихий фолбэк), так что доход
до таблицы уже означает, что кассеты нашлись, а красный вердикт — про путь, не про miss.
"""

import argparse
import asyncio

from app.config import get_settings
from app.domain.gate import build_gate_report
from app.workflow.fixtures import load_requests
from app.workflow.golden import load_golden
from app.workflow.runner import records_path, run_batch, write_records


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="path-gate",
        description="Гейт маршрутизации: путь пачки vs golden. Exit≠0 при регрессии.",
    )
    parser.add_argument("--ids", default=None, help="через запятую — сузить пачку (демо subset)")
    args = parser.parse_args()

    settings = get_settings()
    requests = load_requests(settings.fixtures_dir / "requests-base.jsonl")
    golden = load_golden(settings.fixtures_dir / "golden-base.jsonl")
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        requests = [r for r in requests if r.id in wanted]
        golden = [g for g in golden if g.request_id in wanted]

    records = asyncio.run(run_batch(requests, settings=settings))
    write_records(records, records_path(settings))
    report = build_gate_report({r.request_id: r.trace for r in records}, golden)
    print(f"набор кассет: {settings.cassette_set}\n")
    print(report.render())
    raise SystemExit(0 if report.passed else 1)


if __name__ == "__main__":
    main()
