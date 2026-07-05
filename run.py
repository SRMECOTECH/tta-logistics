"""One-command launcher: starts the FastAPI backend, the MCP server (streamable
HTTP) and the Streamlit frontend.

    python run.py
"""
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PY = sys.executable
API = "http://127.0.0.1:8000"

procs = []


def main() -> None:
    print("▶ Starting FastAPI backend on :8000 …")
    procs.append(subprocess.Popen(
        [PY, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=ROOT,
    ))

    for _ in range(60):
        try:
            r = requests.get(f"{API}/health", timeout=2)
            if r.ok:
                print(f"✔ Backend ready — {r.json()['rows']} trips in database")
                break
        except requests.RequestException:
            time.sleep(1)
    else:
        print("✖ Backend did not come up; check the console above.")

    print("▶ Starting MCP server (streamable HTTP) on :8010 …")
    procs.append(subprocess.Popen(
        [PY, "-m", "mcp_server", "--http", "--port", "8010"],
        cwd=ROOT,
    ))

    print("▶ Starting Streamlit frontend on :8501 …")
    dashboard = subprocess.Popen(
        [PY, "-m", "streamlit", "run", str(ROOT / "frontend" / "Home.py"),
         "--server.port", "8501"],
        cwd=ROOT,
    )
    procs.append(dashboard)

    print("▶ Starting MCP client demo app on :8020 …")
    procs.append(subprocess.Popen(
        [PY, "-m", "streamlit", "run", str(ROOT / "mcp_client_app" / "app.py"),
         "--server.port", "8020"],
        cwd=ROOT,
    ))

    print("\n✅ Dashboard http://localhost:8501  ·  REST/Swagger http://127.0.0.1:8000/docs"
          "  ·  MCP http://127.0.0.1:8010/mcp  ·  MCP client app http://localhost:8020"
          " — Ctrl+C stops all services.\n")
    try:
        dashboard.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
