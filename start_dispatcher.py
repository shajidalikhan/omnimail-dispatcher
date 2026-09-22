"""OmniMail Dispatcher - Local Mode Launcher."""
from pathlib import Path
import sys

# Add root directory to sys.path
root_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(root_dir))

if __name__ == "__main__":
    import run_local
    run_local.main()
