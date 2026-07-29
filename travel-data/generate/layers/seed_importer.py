import csv
from pathlib import Path

from ..config import LAYERS, SEEDS_DIR
from ..db import db
from ..progress import (
    advance_table_progress,
    finish_table_progress,
    start_table_progress,
)


class SeedImporter:
    """种子数据导入器。"""

    LAYER_DIRS = {
        1: "1_dimension",
        2: "2_product",
        3: "3_supply",
        4: "4_user",
        5: "5_marketing",
        6: "6_trade",
    }

    def __init__(self, seeds_dir: Path | None = None):
        self.seeds_dir = seeds_dir or SEEDS_DIR

    def get_table_dir(self, layer: int, table_name: str) -> Path:
        dir_name = self.LAYER_DIRS.get(layer, f"{layer}_layer")
        return self.seeds_dir / dir_name / f"{table_name}.csv"

    def load_csv(
        self, file_path: Path, table_name: str
    ) -> tuple[list[str], list[list]]:
        headers: list[str] = []
        rows: list[list] = []
        with open(file_path, "r", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            headers = next(reader)
            for row in reader:
                normalized = []
                for _, value in zip(headers, row):
                    if value in {"", "NULL"}:
                        normalized.append(None)
                    else:
                        normalized.append(value)
                rows.append(normalized)
        return headers, rows

    def build_insert_sql(self, table_name: str, columns: list[str]) -> str:
        cols = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        return f"INSERT INTO `{table_name}` ({cols}) VALUES ({placeholders})"

    def truncate_table(self, table_name: str) -> None:
        db.execute("SET FOREIGN_KEY_CHECKS = 0")
        db.execute(f"TRUNCATE TABLE `{table_name}`")
        db.execute("SET FOREIGN_KEY_CHECKS = 1")

    def require_table_file(self, table_name: str, layer: int) -> Path:
        file_path = self.get_table_dir(layer, table_name)
        if not file_path.exists():
            raise FileNotFoundError(
                f"missing required seed file for layer {layer} table `{table_name}`: {file_path}"
            )
        return file_path

    def import_table(self, table_name: str, layer: int, clear: bool = True) -> int:
        file_path = self.get_table_dir(layer, table_name)
        if not file_path.exists():
            return 0

        if clear:
            self.truncate_table(table_name)

        columns, rows = self.load_csv(file_path, table_name)
        if not rows:
            return 0

        start_table_progress(table_name, len(rows))
        count = 0
        try:
            count = db.executemany(self.build_insert_sql(table_name, columns), rows)
            advance_table_progress(table_name, count)
        finally:
            finish_table_progress(table_name, count)
        return count

    def import_required_table(
        self, table_name: str, layer: int, clear: bool = True
    ) -> int:
        file_path = self.require_table_file(table_name, layer)

        if clear:
            self.truncate_table(table_name)

        columns, rows = self.load_csv(file_path, table_name)
        if not rows:
            raise ValueError(
                f"required seed file for layer {layer} table `{table_name}` is empty: {file_path}"
            )

        start_table_progress(table_name, len(rows))
        count = 0
        try:
            count = db.executemany(self.build_insert_sql(table_name, columns), rows)
            advance_table_progress(table_name, count)
        finally:
            finish_table_progress(table_name, count)
        return count

    def import_layer(self, layer: int) -> dict[str, int]:
        layer_info = LAYERS.get(layer)
        if not layer_info:
            raise ValueError(f"unknown layer: {layer}")

        results: dict[str, int] = {}
        for table in layer_info["tables"]:
            results[table] = self.import_table(table, layer)
        return results

    def import_required_layer(self, layer: int) -> dict[str, int]:
        layer_info = LAYERS.get(layer)
        if not layer_info:
            raise ValueError(f"unknown layer: {layer}")

        results: dict[str, int] = {}
        for table in layer_info["tables"]:
            results[table] = self.import_required_table(table, layer)
        return results
