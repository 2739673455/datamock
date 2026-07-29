"""数据生成器基类。"""

from abc import ABC, abstractmethod
from typing import Iterable

from ..config import LAYERS
from ..generator_support import bulk_insert_stream
from ..progress import (
    complete_progress_tasks,
    console_print,
    is_table_completed,
    reset_progress_tasks,
)


class BaseGenerator(ABC):
    """数据生成器基类。"""

    layer: int = 0
    layer_name: str = ""

    def log(self, message: str) -> None:
        console_print(message)

    def header(self) -> None:
        reset_progress_tasks()
        name = self.layer_name or LAYERS[self.layer]["name"]
        console_print(f"\n{'=' * 64}")
        console_print(f"Layer {self.layer}: {name}")
        console_print(f"{'=' * 64}")

    def log_table_counts(self, counts: dict[str, int]) -> None:
        for table in LAYERS[self.layer]["tables"]:
            if not is_table_completed(table):
                console_print(f"  [OK] {table}: {counts.get(table, 0)} rows")
        complete_progress_tasks()

    def stream_rows(
        self,
        sql: str,
        rows: Iterable[tuple],
        *,
        total_rows: int | None = None,
        build_step_name: str | None = None,
    ) -> int:
        return bulk_insert_stream(
            sql,
            rows,
            total_rows=total_rows,
            build_step_name=build_step_name,
        )

    @abstractmethod
    def run(self) -> None:
        """执行数据生成。"""
