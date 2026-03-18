"""AI Employee Silver — Main entry point.

Starts all Silver tier watchers (FileSystem + Gmail).
For full orchestration including scheduling and HITL, use orchestrator.py.
"""

import sys
from pathlib import Path

# Ensure silver/ is on the path when run directly
_silver_dir = Path(__file__).resolve().parent.parent
if str(_silver_dir) not in sys.path:
    sys.path.insert(0, str(_silver_dir))

from src.core.config import config
from src.utils.logger import setup_logging


def main():
    """Start the AI Employee Silver system via the orchestrator."""
    setup_logging()
    config.ensure_directories()

    # Delegate to the full orchestrator
    import orchestrator
    orchestrator.main()


if __name__ == "__main__":
    main()
