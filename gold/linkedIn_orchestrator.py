
from orchestrator import ApprovalWatcher
from src.core.config import config
from src.utils.logger import setup_logging
setup_logging()

aw = ApprovalWatcher()
for f in config.approved_path.glob('LINKEDIN_POST_*.md'):
    print(f'Processing: {f.name}')
    aw._handle_approved(f)