"""Vercel entrypoint: exposes the ASGI app as a module-level ``app``."""
import sys
from pathlib import Path

# Make ``src/mars`` importable even if the project itself isn't pip-installed.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mars.api.app import create_app  # noqa: E402

app = create_app()
