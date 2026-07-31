from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Local data folders (preferred for deployment)
DATA_DELSYS = ROOT / "data" / "delsys"
DATA_TXT = ROOT / "data" / "txt"

# Optional fallbacks to existing sibling projects during development
FALLBACK_DELSYS = ROOT.parent / "emgcsv(delsys)" / "data"
FALLBACK_TXT = ROOT.parent / "emgtxt2chart" / "data"

RESOURCE_DIR = ROOT
MAX_PLOT_POINTS = 5000


def ensure_data_dirs() -> None:
    DATA_DELSYS.mkdir(parents=True, exist_ok=True)
    DATA_TXT.mkdir(parents=True, exist_ok=True)


def resolve_delsys_dirs() -> list[Path]:
    ensure_data_dirs()
    dirs = [DATA_DELSYS]
    if FALLBACK_DELSYS.exists():
        dirs.append(FALLBACK_DELSYS)
    return dirs


def resolve_txt_dirs() -> list[Path]:
    ensure_data_dirs()
    dirs = [DATA_TXT]
    if FALLBACK_TXT.exists():
        dirs.append(FALLBACK_TXT)
    return dirs
