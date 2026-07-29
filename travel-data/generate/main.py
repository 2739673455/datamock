"""数据生成入口。"""

import argparse

from .config import GENERATION_DEFAULTS, generation_profile
from .db import close_db, init_db, interrupt_db
from .layers.layer1 import Layer1Generator
from .layers.layer2 import Layer2Generator
from .layers.layer3 import Layer3Generator
from .layers.layer4 import Layer4Generator
from .layers.layer5 import Layer5Generator
from .layers.layer6 import Layer6Generator
from .layers.validations import validate_stage7_acceptance
from .progress import console_print, progress_context

GENERATORS = (
    Layer1Generator,
    Layer2Generator,
    Layer3Generator,
    Layer4Generator,
    Layer5Generator,
    Layer6Generator,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Travel data generator")
    parser.add_argument(
        "--profile",
        choices=("smoke", "full"),
        default="full",
        help="generation profile",
    )
    return parser.parse_args()


def run_generators() -> None:
    for generator_cls in GENERATORS:
        generator_cls().run()


def run_acceptance() -> None:
    console_print("\n" + "=" * 64)
    console_print("Stage 7: 最终验收")
    console_print("=" * 64)
    checks = validate_stage7_acceptance()
    for check in checks:
        console_print(f"  [OK] acceptance: {check}")


def main() -> None:
    args = parse_args()
    interrupted = False
    init_db()
    try:
        with generation_profile(args.profile):
            with progress_context():
                console_print(
                    f"Generation profile: {args.profile} -> {GENERATION_DEFAULTS}"
                )
                run_generators()
                run_acceptance()
    except KeyboardInterrupt:
        interrupted = True
        console_print(
            "\nGeneration interrupted by user, interrupting database connection..."
        )
        interrupt_db()
        raise SystemExit(130)
    finally:
        if not interrupted:
            close_db()


if __name__ == "__main__":
    main()
