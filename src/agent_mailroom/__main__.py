from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    host = os.environ.get("MAILROOM_HOST", "127.0.0.1")
    port = int(os.environ.get("MAILROOM_PORT", "8000"))
    uvicorn.run("agent_mailroom.api.app:create_app", factory=True, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
