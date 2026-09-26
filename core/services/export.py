"""Админ-выгрузка в CSV. Метрики воронки смотрим в Metabase поверх той же Postgres."""

from __future__ import annotations

import csv
import io
from typing import Any, Protocol


class ExportSource(Protocol):
    async def sessions(self) -> list[dict[str, Any]]: ...

    async def checkins(self) -> list[dict[str, Any]]: ...

    async def funnel(self) -> list[dict[str, Any]]: ...


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _flatten(v) for k, v in row.items()})
    return buffer.getvalue()


def _flatten(value: Any) -> Any:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    if hasattr(value, "value"):
        return value.value
    return value


class ExportService:
    def __init__(self, source: ExportSource) -> None:
        self._source = source

    async def sessions_csv(self) -> str:
        return rows_to_csv(await self._source.sessions())

    async def checkins_csv(self) -> str:
        return rows_to_csv(await self._source.checkins())

    async def funnel(self) -> list[dict[str, Any]]:
        return await self._source.funnel()
