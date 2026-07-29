"""第二层：商品主数据。"""

from ..generator_support import reset_tables
from .base import BaseGenerator
from .seed_importer import SeedImporter
from .validations import validate_layer2


class Layer2Generator(BaseGenerator):
    layer = 2
    layer_name = "商品主数据"

    def run(self) -> None:
        self.header()
        reset_tables(
            "transfer_service_area_rules",
            "transfer_services",
            "bus_routes",
            "train_routes",
            "flight_routes",
            "scenic_booking_rules",
            "scenic_ticket_types",
            "scenic_spots",
            "hotel_booking_rules",
            "hotel_room_types",
            "hotels",
        )
        counts = SeedImporter().import_required_layer(self.layer)
        self.log_table_counts(counts)

        checks = validate_layer2()
        for check in checks:
            self.log(f"  [OK] validation: {check}")
