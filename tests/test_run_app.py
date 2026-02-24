import subprocess
import sys
from pathlib import Path


def test_app_starts_without_immediate_crash():
    """
    Uruchamia `python app.py` na krótko i sprawdza, czy program nie kończy się od razu błędem.
    Jeśli Twoja aplikacja to serwer, to go ubijamy po 2 sekundach.
    """
    project_root = Path(__file__).resolve().parents[1]
    app_py = project_root / "app.py"

    assert app_py.exists(), "Nie znaleziono app.py w katalogu głównym projektu."

    proc = subprocess.Popen(
        [sys.executable, str(app_py)],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # daj aplikacji 2 sekundy na start
        proc.wait(timeout=2)
        # jeśli się zakończyła sama w 2 sekundy, to raczej błąd (albo program nie jest serwerem)
        # sprawdzamy kod wyjścia:
        assert proc.returncode == 0, f"Aplikacja zakończyła się błędem:\n{proc.stderr.read()}"
    except subprocess.TimeoutExpired:
        # normalne dla serwera: działa dalej, więc jest OK
        proc.terminate()
