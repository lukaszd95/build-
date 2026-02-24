import subprocess
import sys
from pathlib import Path


def test_app_py_is_valid_python():
    """
    Smoke test: sprawdza, czy app.py jest poprawnym plikiem Pythona (da się go skompilować).
    Nie uruchamia serwera, więc test nie będzie się wieszał.
    """
    project_root = Path(__file__).resolve().parents[1]
    app_py = project_root / "app.py"

    assert app_py.exists(), "Nie znaleziono app.py w katalogu głównym projektu."

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(app_py)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"app.py ma błąd składni:\n{result.stderr}"
