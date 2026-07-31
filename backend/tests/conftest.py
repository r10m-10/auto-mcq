import os
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Redirect cwd BEFORE `main` is imported so its `DB_PATH = "app.db"` and
# init_db() land in a throwaway temp dir — the real repo/backend app.db is
# never touched by tests.
os.chdir(tempfile.mkdtemp(prefix="automcq_test_"))

from main import app  # noqa: E402
