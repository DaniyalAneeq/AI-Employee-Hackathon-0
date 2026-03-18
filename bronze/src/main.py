"""AI Employee Bronze — Main entry point.

Starts the File System Watcher and keeps it running.
The orchestrator can also be used for more advanced control.
"""

import sys
from pathlib import Path

# Ensure bronze/ is on the path when run directly
bronze_dir = Path(__file__).resolve().parent.parent
if str(bronze_dir) not in sys.path:
    sys.path.insert(0, str(bronze_dir))

from src.core.config import config
from src.utils.logger import setup_logging
from src.watchers.filesystem_watcher import FileSystemWatcher


def main():
    """Start the AI Employee Bronze system."""
    setup_logging()
    config.ensure_directories()

    print("=" * 55)
    print("  AI Employee — Bronze Tier")
    print("=" * 55)
    print(f"  Vault:        {config.vault_path}")
    print(f"  Drop Folder:  {config.drop_folder_path}")
    print(f"  Dry Run:      {config.dry_run}")
    print(f"  Log Level:    {config.log_level}")
    print("=" * 55)
    print()
    print("  Drop files into the drop folder to trigger processing.")
    print("  Then use the vault-processor skill to process items:")
    print("    /vault-processor")
    print()
    print("  Press Ctrl+C to stop.")
    print()

    watcher = FileSystemWatcher()
    watcher.run_forever()


if __name__ == "__main__":
    main()
