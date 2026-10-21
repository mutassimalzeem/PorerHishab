"""Manual Uvicorn startup check.

Starts the API on a free port, probes /openapi.json, then shuts down.
Usage: python scripts/check_uvicorn.py
"""

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import uvicorn  # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
RESULT = {}


def probe():
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/openapi.json", timeout=3) as r:
                spec = json.loads(r.read().decode())
            RESULT["title"] = spec["info"]["title"]
            RESULT["paths"] = len(spec["paths"])
            RESULT["ok"] = True
            return
        except Exception:
            time.sleep(0.5)
    RESULT["ok"] = False
    RESULT["error"] = "server did not become ready within 15s"


def main():
    threading.Thread(target=probe, daemon=True).start()
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    threading.Timer(8, lambda: setattr(server, "should_exit", True)).start()
    server.run()

    if RESULT.get("ok"):
        print(f"UVICORN OK  title={RESULT['title']}  paths={RESULT['paths']}")
        return 0
    print(f"UVICORN FAIL  {RESULT.get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
