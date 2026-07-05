"""
Fix all dashboard files so set_page_config is always the first Streamlit command.

Root cause: triple-quoted docstrings BEFORE import streamlit confuse Streamlit into
thinking something was already output before set_page_config.

Fix: remove leading docstrings, put sys.path first, then the clean file body.
"""
import re
from pathlib import Path

root = Path(__file__).parent.parent

SYSPATH_HOME = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
)
SYSPATH_PAGE = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.dirname(os.path.dirname("
    "os.path.dirname(os.path.abspath(__file__)))))\n"
)

files = {root / "dashboard" / "Home.py": SYSPATH_HOME}
for p in (root / "dashboard" / "pages").glob("*.py"):
    files[p] = SYSPATH_PAGE

for fpath, syspath in files.items():
    content = fpath.read_text(encoding="utf-8")

    # 1. Remove any previous sys.path injections we added
    content = re.sub(
        r"import sys, os\nsys\.path\.insert\(0, os\.path\.[^\n]+\)\n",
        "", content
    )

    # 2. Remove leading module docstrings (triple-quoted strings before any import)
    #    These appear as text in Streamlit before set_page_config
    content = re.sub(r'^\s*""".*?"""\s*\n', "", content, count=1, flags=re.DOTALL)
    content = re.sub(r"^\s*'''.*?'''\s*\n", "", content, count=1, flags=re.DOTALL)
    content = content.lstrip("\n")

    # 3. New file: sys.path first, then original content
    new_content = syspath + content
    fpath.write_text(new_content, encoding="utf-8")

    # 4. Verify ordering
    lines = [l for l in new_content.split("\n") if l.strip() and not l.startswith("#")]
    sp_idx  = next((i for i, l in enumerate(lines) if "import streamlit" in l), -1)
    pg_idx  = next((i for i, l in enumerate(lines) if "set_page_config" in l), -1)
    ok = "OK" if sp_idx < pg_idx else "WARN"
    print(f"[{ok}] {fpath.name:45s}  streamlit@{sp_idx}  set_page_config@{pg_idx}")

print("\nAll dashboard files patched.")
