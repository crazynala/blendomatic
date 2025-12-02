import os
from pathlib import Path
from typing import Optional, Union


CODE_ROOT_ENV = "BLENDOMATIC_ROOT"           # Root of this code repo (preferred)
ASSETS_ROOT_ENV = "BLENDER_PROJECT_ROOT"     # Root for Blender .blend and image assets
RENDER_CONFIG_OVERRIDE_ENV = "BLENDOMATIC_RENDER_CONFIG"
GARMENTS_OVERRIDE_ENV = "BLENDOMATIC_GARMENTS_DIR"
FABRICS_OVERRIDE_ENV = "BLENDOMATIC_FABRICS_DIR"


def _env_path(var: str) -> Optional[Path]:
    val = os.environ.get(var)
    if val:
        p = Path(os.path.expanduser(os.path.expandvars(val))).resolve()
        return p
    return None


def _detect_project_root_from_here(start: Optional[Path] = None) -> Path:
    here = (start or Path(__file__).resolve()).parent
    markers = {"render_config.json", "blender_tui.py", ".git"}
    for d in [here, *here.parents]:
        try:
            names = {p.name for p in d.iterdir()}
        except Exception:
            continue
        if (".git" in names) or ({"render_config.json", "blender_tui.py"}.issubset(names)):
            return d
    # Fallback to current working directory if nothing else
    return Path.cwd().resolve()


def get_code_root() -> Path:
    """Return the code/project root directory.

    Priority:
    1) Environment variable BLENDOMATIC_ROOT
    2) Heuristic search upwards from this file for repo markers
    3) Current working directory
    """
    return _env_path(CODE_ROOT_ENV) or _detect_project_root_from_here()


def get_assets_root() -> Path:
    """Return the assets root directory used to resolve paths in JSON (blend/textures).

    Priority:
    1) Environment variable BLENDER_PROJECT_ROOT
    2) Fallback to code root
    """
    return _env_path(ASSETS_ROOT_ENV) or get_code_root()


def resolve_project_path(path_like: Union[str, Path, None]) -> Optional[Path]:
    """Resolve a path relative to the project root if not absolute.

    - Expands environment variables and ~
    - If absolute, returns as-is
    - If relative, returns `get_project_root() / relative`
    - Returns None if input is None/empty
    """
    if not path_like:
        return None
    s = str(path_like)
    s = os.path.expanduser(os.path.expandvars(s))
    p = Path(s)
    if p.is_absolute():
        return p
    # Resolve relative paths against the ASSETS root
    return get_assets_root() / p


# Common locations in this repo (code), resolved against code root
CODE_ROOT: Path
ASSETS_ROOT: Path
RENDER_CONFIG_PATH: Path
GARMENTS_DIR: Path
FABRICS_DIR: Path
RENDERS_DIR: Path
DEBUG_DIR: Path
RUNS_DIR: Path

def _simple_load_dotenv(dotenv_path: Path):
    """Lightweight .env loader (key=value) used if python-dotenv isn't invoked earlier."""
    if not dotenv_path.exists():
        return
    try:
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass

def refresh_roots():
    """(Re)compute root directories after environment changes.

    Call this after loading .env so BLENDER_PROJECT_ROOT is respected.
    """
    global CODE_ROOT, ASSETS_ROOT
    global RENDER_CONFIG_PATH, GARMENTS_DIR, FABRICS_DIR, RENDERS_DIR, DEBUG_DIR, RUNS_DIR
    CODE_ROOT = get_code_root()
    ASSETS_ROOT = get_assets_root()

    render_config_override = _env_path(RENDER_CONFIG_OVERRIDE_ENV)
    garments_override = _env_path(GARMENTS_OVERRIDE_ENV)
    fabrics_override = _env_path(FABRICS_OVERRIDE_ENV)

    RENDER_CONFIG_PATH = render_config_override or (CODE_ROOT / "render_config.json")
    GARMENTS_DIR = garments_override or (CODE_ROOT / "garments")
    FABRICS_DIR = fabrics_override or (CODE_ROOT / "fabrics")
    RENDERS_DIR = CODE_ROOT / "renders"
    DEBUG_DIR = CODE_ROOT / "debug"
    RUNS_DIR = CODE_ROOT / "runs"

# Attempt lightweight .env load BEFORE initial root computation
_simple_load_dotenv(Path(__file__).resolve().parent / '.env')

# Initialize once at import; can be refreshed later (after external dotenv load)
refresh_roots()

