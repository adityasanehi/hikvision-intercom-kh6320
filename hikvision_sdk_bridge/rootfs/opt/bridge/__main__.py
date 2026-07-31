"""Entry point for the Hikvision SDK bridge add-on."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from server import BridgeServer

DEFAULT_OPTIONS = {
    "listen_port": 8199,
    "log_level": "info",
    "sdk_dir": "/opt/hcnetsdk",
}


def load_options() -> dict:
    opts = dict(DEFAULT_OPTIONS)
    path = "/data/options.json"
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                opts.update({k: v for k, v in json.load(fh).items() if v is not None})
        except (OSError, json.JSONDecodeError):
            pass
    # env overrides (useful when run as a plain container)
    if os.environ.get("LISTEN_PORT"):
        opts["listen_port"] = int(os.environ["LISTEN_PORT"])
    if os.environ.get("SDK_DIR"):
        opts["sdk_dir"] = os.environ["SDK_DIR"]
    if os.environ.get("LOG_LEVEL"):
        opts["log_level"] = os.environ["LOG_LEVEL"]
    return opts


def main() -> None:
    opts = load_options()
    logging.basicConfig(
        level=getattr(logging, str(opts["log_level"]).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("bridge")
    log.info("Starting Hikvision SDK bridge, options=%s", {
        k: v for k, v in opts.items()
    })

    server = BridgeServer(sdk_dir=opts["sdk_dir"], port=int(opts["listen_port"]))
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
