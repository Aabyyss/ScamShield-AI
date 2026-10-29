"""One-click launcher for ScamShield AI.

Starts the local Streamlit app on a free port, makes sure Ollama is awake, opens the browser,
and then gets out of the way. Double-clicking the desktop shortcut ends up here.

    python launcher.py              # start (or reuse) and open the browser
    python launcher.py --no-browser # start without opening a tab
    python launcher.py --port 8501  # force a port
    python launcher.py --restart    # stop the recorded server and start a fresh one
    python launcher.py --stop       # stop the server recorded in data/launcher.json

The server is detached, so closing the console window does not kill the app.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATE_FILE = DATA / "launcher.json"
LOG_FILE = DATA / "launcher.log"
APP_FILE = ROOT / "app.py"
REQUIREMENTS = ROOT / "requirements.txt"

PREFERRED_PORT = 8501
PORT_ATTEMPTS = 20
START_TIMEOUT = 75

IS_WINDOWS = os.name == "nt"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


def log(message: str) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
    print(message, flush=True)


def report_error(message: str) -> None:
    """Show the failure even when launched with pythonw (no console)."""
    log(f"ERROR: {message}")
    if not IS_WINDOWS or sys.stdout is not None:
        return
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("ScamShield AI could not start", message)
        root.destroy()
    except Exception:  # noqa: BLE001 - a dialog is best effort
        pass


def port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def pick_port(preferred: int | None = None) -> int:
    start = preferred or PREFERRED_PORT
    for port in range(start, start + PORT_ATTEMPTS):
        if not port_in_use(port):
            return port
    raise RuntimeError(
        f"No free port between {start} and {start + PORT_ATTEMPTS - 1}. "
        "Close some Streamlit instances and try again."
    )


def healthy(port: int, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=timeout
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if IS_WINDOWS:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stop_server() -> bool:
    state = read_state()
    pid = state.get("pid")
    if not pid or not pid_alive(int(pid)):
        log("No running ScamShield server was recorded.")
        return False
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(int(pid), 15)
        except OSError as exc:
            log(f"Could not stop PID {pid}: {exc}")
            return False
    log(f"Stopped ScamShield (PID {pid}).")
    try:
        STATE_FILE.unlink()
    except OSError:
        pass
    return True


# --------------------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------------------


def ensure_dependencies() -> None:
    try:
        import streamlit  # noqa: F401
        return
    except ImportError:
        pass

    log("First run: installing Python packages (this can take a few minutes)…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Installing requirements failed. Open a terminal in the project folder and run "
            "`pip install -r requirements.txt` to see the full error."
        )
    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Streamlit is still not importable after installation. Check the pip output above."
        ) from exc


def ollama_reachable(timeout: float = 1.5) -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip()
    if not host.startswith("http"):
        host = "http://" + host
    try:
        with urllib.request.urlopen(f"{host.rstrip('/')}/api/version", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def ensure_ollama() -> None:
    if ollama_reachable():
        return
    executable = shutil.which("ollama")
    if not executable:
        log("Ollama is not installed. The app will run with the rules engine only.")
        return

    log("Waking up Ollama…")
    DATA.mkdir(parents=True, exist_ok=True)
    flags = (DETACHED_PROCESS | CREATE_NO_WINDOW) if IS_WINDOWS else 0
    with LOG_FILE.open("a", encoding="utf-8") as log_handle:
        log_handle.write("\n--- ollama serve ---\n")
        try:
            subprocess.Popen(
                [executable, "serve"],
                cwd=ROOT,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=flags,
                start_new_session=not IS_WINDOWS,
            )
        except OSError as exc:
            log(f"Could not start Ollama ({exc}). Continuing with rules only.")
            return

    for _ in range(24):
        if ollama_reachable():
            log("Ollama is ready.")
            return
        time.sleep(0.5)
    log("Ollama did not answer in time. The rules engine still works.")


def pythonw() -> str:
    if IS_WINDOWS:
        candidate = Path(sys.executable).with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return sys.executable


def start_server(port: int) -> subprocess.Popen:
    DATA.mkdir(parents=True, exist_ok=True)
    flags = (DETACHED_PROCESS | CREATE_NO_WINDOW) if IS_WINDOWS else 0
    command = [
        pythonw(),
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.headless=true",
        "--server.port",
        str(port),
        "--server.address",
        "127.0.0.1",
    ]
    log(f"Starting ScamShield on port {port}…")
    with LOG_FILE.open("a", encoding="utf-8") as log_handle:
        log_handle.write(f"\n--- start {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            start_new_session=not IS_WINDOWS,
        )
    return process


def wait_until_ready(port: int, process: subprocess.Popen, timeout: int = START_TIMEOUT) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if healthy(port):
            return
        if process.poll() is not None:
            tail = ""
            try:
                tail = "\n".join(LOG_FILE.read_text(encoding="utf-8").splitlines()[-12:])
            except OSError:
                pass
            raise RuntimeError(
                "The app stopped while starting. Recent log lines:\n\n" + tail
            )
        time.sleep(0.6)
    raise RuntimeError(
        f"The app did not answer on port {port} within {timeout} seconds. "
        f"Check {LOG_FILE}."
    )


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch ScamShield AI in your browser.")
    parser.add_argument("--port", type=int, help="Port to use (default: 8501 or the next free one)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    parser.add_argument("--restart", action="store_true", help="Restart the recorded server")
    parser.add_argument("--stop", action="store_true", help="Stop the recorded server and exit")
    args = parser.parse_args(argv)

    if args.stop:
        stop_server()
        return 0

    if args.restart:
        stop_server()
        time.sleep(1.0)

    state = read_state()
    recorded_port = state.get("port")
    if not args.port and not args.restart and recorded_port and healthy(int(recorded_port)):
        url = f"http://127.0.0.1:{recorded_port}"
        log(f"ScamShield is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    try:
        ensure_dependencies()
        ensure_ollama()
        port = args.port or pick_port()
        if port_in_use(port):
            raise RuntimeError(
                f"Port {port} is already in use. Close that program or pass --port."
            )
        process = start_server(port)
        wait_until_ready(port, process)
    except Exception as exc:  # noqa: BLE001 - the launcher is the user's only surface
        report_error(str(exc))
        return 1

    url = f"http://127.0.0.1:{port}"
    write_state(
        {
            "port": port,
            "pid": process.pid,
            "url": url,
            "started": datetime.now().isoformat(timespec="seconds"),
        }
    )
    log(f"ScamShield is running at {url}")
    log("Close this window any time — the app keeps running. Use launcher.py --stop to quit it.")
    if not args.no_browser:
        webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
