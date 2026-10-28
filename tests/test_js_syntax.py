"""A syntax error in one front-end module silently breaks the whole page (the shell then stays
untranslated), and none of the Python tests would notice."""
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "app" / "static" / "js"
MODULES = sorted(STATIC.rglob("*.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("module", MODULES, ids=lambda p: str(p.relative_to(STATIC)))
def test_module_parses_as_an_es_module(module, tmp_path):
    copy = tmp_path / "m.mjs"            # .mjs: parsed as an ES module like the browser does
    copy.write_text(module.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:400]
