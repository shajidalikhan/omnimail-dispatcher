"""Start OmniMail Dispatcher in Single-Machine Local Mode (127.0.0.1 only)."""
import os
import sys
import time
import socket
import threading
import webbrowser
from pathlib import Path

# Force LOCAL_MODE for local desktop runs
os.environ["LOCAL_MODE"] = "true"

import uvicorn


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start_port: int = 8000) -> int:
    port = start_port
    while is_port_in_use(port):
        port += 1
    return port


def open_browser(url: str, delay: float = 1.0) -> None:
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[!] Could not open browser automatically: {e}")


def main() -> None:
    # Ensure current directory is in sys.path
    root_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(root_dir))

    port = find_free_port(8000)
    url = f"http://127.0.0.1:{port}"

    print("=" * 64)
    print("  OmniMail Dispatcher - Local Mode")
    print("=" * 64)
    print(f"[*] Starting local server on: {url}")
    print("[*] Credentials will be safely persisted to your local .env file.")
    print("[*] Opening your web browser automatically...\n")

    threading.Thread(target=open_browser, args=(url,), daemon=True).start()
    uvicorn.run("backend.app:app", host="127.0.0.1", port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
