from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_DIR = ROOT / "spcrawler"
sys.path.insert(0, str(ENGINE_DIR))

from spcrawler.runner import main


if __name__ == "__main__":
    main()
