"""Add pipeline/ to sys.path so test imports resolve without installing the package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
