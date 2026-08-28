from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .account import ServerConfig
from .server import LaserTcpCentralGateway

PROJECT_DIR = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BSL v68 server emulator")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9339)
    parser.add_argument("--reset", action="store_true", help="start a new local profile")
    parser.add_argument("--config", type=Path, default=PROJECT_DIR / "config.json")
    parser.add_argument("--data-dir", type=Path, default=PROJECT_DIR / "data")
    parser.add_argument(
        "--catalog-info",
        nargs="?",
        type=Path,
        const=PROJECT_DIR.parent / "com.bsl.v68-rev2_sign_sign_src",
        help="print APK csv_logic table counts and exit",
    )
    parser.add_argument(
        "--apk-info",
        nargs="?",
        type=Path,
        const=PROJECT_DIR.parent / "com.bsl.v68-rev2_sign_sign_src",
        help="inspect unpacked/decompiled APK and exit",
    )
    parser.add_argument(
        "--verify-assets",
        nargs="?",
        type=Path,
        const=PROJECT_DIR.parent / "com.bsl.v68-rev2_sign_sign_src" / "assets",
        help="verify unpacked assets against fingerprint.json and exit",
    )
    parser.add_argument(
        "--roll-reward",
        nargs="?",
        type=Path,
        const=PROJECT_DIR.parent / "com.bsl.v68-rev2_sign_sign_src",
        help="roll one reward from the APK Starr Drop tables and exit",
    )
    parser.add_argument("--reward-rarity", type=int, choices=range(5))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.apk_info is not None:
        from dataclasses import asdict

        from .apk import inspect_apk

        values = asdict(inspect_apk(args.apk_info))
        values["root"] = str(values["root"])
        print(json.dumps(values, ensure_ascii=False, indent=2))
        return
    if args.verify_assets is not None:
        from dataclasses import asdict

        from .fingerprint import ContentFingerprint

        fingerprint = ContentFingerprint.load(args.verify_assets)
        result = asdict(fingerprint.verify(args.verify_assets))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.roll_reward is not None:
        from dataclasses import asdict

        from .rewards import RandomRewardEngine
        from .static_data import StaticDataCatalog

        roll = RandomRewardEngine(StaticDataCatalog(args.roll_reward)).roll(
            args.reward_rarity
        )
        print(json.dumps(asdict(roll), ensure_ascii=False, indent=2))
        return
    if args.catalog_info is not None:
        from .static_data import StaticDataCatalog

        catalog = StaticDataCatalog(args.catalog_info)
        names = (
            "characters", "cards", "skins", "emotes", "sprays",
            "player_thumbnails", "player_titles", "alliance_badges", "regions",
        )
        print(json.dumps(catalog.summary(*names), ensure_ascii=False, indent=2))
        return
    config = ServerConfig.load(args.config)
    try:
        gateway = LaserTcpCentralGateway(
            args.host,
            args.port,
            config,
            args.data_dir / "player.json",
            args.reset,
        )
        asyncio.run(gateway.serve_forever())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
