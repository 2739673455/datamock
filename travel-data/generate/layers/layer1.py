"""第一层：维度与基础主数据。"""

from .base import BaseGenerator
from .seed_importer import SeedImporter
from .validations import validate_layer1


class Layer1Generator(BaseGenerator):
    layer = 1
    layer_name = "维度与基础主数据"

    def run(self) -> None:
        self.header()
        self.log_table_counts(SeedImporter().import_required_layer(self.layer))
        checks = validate_layer1()
        for check in checks:
            self.log(f"  [OK] validation: {check}")
