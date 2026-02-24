import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class DwgConverterError(RuntimeError):
    pass


class DwgConverter:
    def convert(self, dwg_path: str, output_dir: str, timeout: int = 120) -> str:
        raise NotImplementedError


@dataclass
class OdaFileConverterDwgConverter(DwgConverter):
    oda_path: str

    def convert(self, dwg_path: str, output_dir: str, timeout: int = 120) -> str:
        dwg_path = os.path.abspath(dwg_path)
        output_dir = os.path.abspath(output_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        input_dir = str(Path(dwg_path).parent)
        command = [
            self.oda_path,
            input_dir,
            output_dir,
            "DXF",
            "ACAD2018",
            "0",
            "1",
        ]

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise DwgConverterError("Konwersja DWG->DXF przekroczyła limit czasu.") from exc
        except FileNotFoundError as exc:
            raise DwgConverterError(
                f"Nie znaleziono ODAFileConverter pod ścieżką: {self.oda_path}."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
            raise DwgConverterError(
                f"Błąd konwersji DWG->DXF przez ODAFileConverter. {stderr}"
            ) from exc

        output_path = Path(output_dir) / (Path(dwg_path).stem + ".dxf")
        if not output_path.exists():
            raise DwgConverterError("Konwerter ODA nie wygenerował pliku DXF.")
        return str(output_path)


@dataclass
class Dwg2DxfConverter(DwgConverter):
    binary_path: str

    def convert(self, dwg_path: str, output_dir: str, timeout: int = 120) -> str:
        output_dir = os.path.abspath(output_dir)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        output_path = Path(output_dir) / (Path(dwg_path).stem + ".dxf")
        command = [self.binary_path, dwg_path, str(output_path)]

        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise DwgConverterError("Konwersja DWG->DXF przekroczyła limit czasu.") from exc
        except FileNotFoundError as exc:
            raise DwgConverterError(
                f"Nie znaleziono konwertera dwg2dxf pod ścieżką: {self.binary_path}."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
            raise DwgConverterError(f"Błąd konwersji DWG->DXF przez dwg2dxf. {stderr}") from exc

        if not output_path.exists():
            raise DwgConverterError("Konwerter dwg2dxf nie wygenerował pliku DXF.")
        return str(output_path)


class NotConfiguredDwgConverter(DwgConverter):
    def convert(self, dwg_path: str, output_dir: str, timeout: int = 120) -> str:
        raise DwgConverterError(
            "Brak skonfigurowanego konwertera DWG. Ustaw ODA_FILE_CONVERTER lub DWG2DXF_PATH."
        )


def _resolve_oda_path(oda_path: str | None) -> str | None:
    if oda_path:
        resolved = shutil.which(oda_path)
        if resolved:
            return resolved
        if Path(oda_path).exists():
            return oda_path
        return None
    return shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")


def _resolve_dwg2dxf_path(dwg2dxf_path: str | None) -> str | None:
    if dwg2dxf_path:
        resolved = shutil.which(dwg2dxf_path)
        if resolved:
            return resolved
        if Path(dwg2dxf_path).exists():
            return dwg2dxf_path
        return None
    return shutil.which("dwg2dxf")


def create_dwg_converter(oda_path: str | None = None, dwg2dxf_path: str | None = None) -> DwgConverter:
    resolved_oda = _resolve_oda_path(oda_path)
    if resolved_oda:
        return OdaFileConverterDwgConverter(resolved_oda)

    resolved_dwg2dxf = _resolve_dwg2dxf_path(dwg2dxf_path)
    if resolved_dwg2dxf:
        return Dwg2DxfConverter(resolved_dwg2dxf)

    return NotConfiguredDwgConverter()
