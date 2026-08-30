from __future__ import annotations

import argparse
import os

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="The Mailroom")
    parser.add_argument("--desktop", action="store_true", help="Open the hardened Electron shell")
    parser.add_argument("--host", default=os.environ.get("MAILROOM_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MAILROOM_PORT", "8000")))
    args, _unknown = parser.parse_known_args()
    os.environ.setdefault("MAILROOM_HOST", args.host)
    os.environ.setdefault("MAILROOM_PORT", str(args.port))
    if args.desktop:
        from agent_mailroom.desktop import run_desktop

        raise SystemExit(run_desktop(host=args.host, port=args.port))
    uvicorn.run(
        "agent_mailroom.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
