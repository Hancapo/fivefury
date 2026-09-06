import subprocess
import sys
from pathlib import Path


def run_python(code: str, *, timeout: float = 15) -> subprocess.CompletedProcess[str]:
    import fivefury

    package_parent = str(Path(fivefury.__file__).resolve().parent.parent)
    bootstrap = f"import sys; sys.path.insert(0, {package_parent!r});\n"
    return subprocess.run(
        [sys.executable, "-I", "-c", bootstrap + code],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
