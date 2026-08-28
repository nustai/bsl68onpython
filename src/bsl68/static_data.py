from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path


def locate_csv_logic(root: str | Path) -> Path:
    """Resolve an APK, unpacked APK, or direct csv_logic directory."""
    root = Path(root).expanduser().resolve()
    candidates = (root, root / "csv_logic", root / "assets" / "csv_logic")
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "characters.csv").is_file():
            return candidate
    raise FileNotFoundError(f"csv_logic not found below {root}")


@dataclass(frozen=True, slots=True)
class StaticDataRow(Mapping[str, str]):
    row_id: int
    values: Mapping[str, str]

    def __getitem__(self, key: str) -> str:
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    @property
    def name(self) -> str:
        return self.values.get("Name", "")

    def integer(self, key: str, default: int = 0) -> int:
        try:
            return int(self.values.get(key, ""))
        except (TypeError, ValueError):
            return default

    def boolean(self, key: str, default: bool = False) -> bool:
        value = self.values.get(key, "").strip().casefold()
        if value in {"true", "1", "yes"}:
            return True
        if value in {"false", "0", "no"}:
            return False
        return default


class CsvTable:
    """Read-only view over one Supercell static-data CSV table."""

    def __init__(self, name: str, field_types: Mapping[str, str], rows: tuple[StaticDataRow, ...]):
        self.name = name
        self.field_types = dict(field_types)
        self.rows = rows
        self._by_name = {row.name.casefold(): row for row in rows if row.name}

    @classmethod
    def load(cls, path: str | Path) -> CsvTable:
        path = Path(path)
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames:
                raise ValueError(f"CSV has no header: {path}")
            try:
                type_row = next(reader)
            except StopIteration as error:
                raise ValueError(f"CSV has no type row: {path}") from error
            field_types = {key: (value or "string") for key, value in type_row.items()}
            rows = tuple(
                StaticDataRow(index, {key: value or "" for key, value in raw.items()})
                for index, raw in enumerate(reader, 1)
            )
        return cls(path.stem, field_types, rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[StaticDataRow]:
        return iter(self.rows)

    def by_id(self, row_id: int) -> StaticDataRow:
        if row_id <= 0:
            raise KeyError(row_id)
        try:
            return self.rows[row_id - 1]
        except IndexError as error:
            raise KeyError(row_id) from error

    def by_name(self, name: str) -> StaticDataRow:
        try:
            return self._by_name[name.casefold()]
        except KeyError as error:
            raise KeyError(name) from error

    def enabled(self) -> tuple[StaticDataRow, ...]:
        return tuple(row for row in self.rows if not row.boolean("Disabled"))


class StaticDataCatalog:
    """Lazy loader for the v68 APK's assets/csv_logic directory."""

    def __init__(self, root: str | Path):
        self.root = locate_csv_logic(root)
        self._tables: dict[str, CsvTable] = {}

    @property
    def table_names(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self.root.glob("*.csv")))

    def table(self, name: str) -> CsvTable:
        key = Path(name).stem.casefold()
        if key not in self._tables:
            path = next((item for item in self.root.glob("*.csv") if item.stem.casefold() == key), None)
            if path is None:
                raise KeyError(name)
            self._tables[key] = CsvTable.load(path)
        return self._tables[key]

    def summary(self, *names: str) -> dict[str, int]:
        selected = names or self.table_names
        return {name: len(self.table(name)) for name in selected}
