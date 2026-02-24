import math

import ezdxf

INSUNITS_SCALE = {
    1: ("inch", 0.0254),
    2: ("foot", 0.3048),
    3: ("mile", 1609.344),
    4: ("mm", 0.001),
    5: ("cm", 0.01),
    6: ("m", 1.0),
    7: ("km", 1000.0),
    8: ("microinch", 0.0000254),
    9: ("mil", 0.0000254),
    10: ("yard", 0.9144),
    11: ("angstrom", 1e-10),
    12: ("nanometer", 1e-9),
    13: ("micron", 1e-6),
    14: ("dm", 0.1),
    15: ("dam", 10.0),
    16: ("hm", 100.0),
    17: ("gm", 1_000_000_000.0),
    18: ("au", 149_597_870_700.0),
    19: ("ly", 9_460_730_472_580_800.0),
    20: ("pc", 30_856_775_814_913_700.0),
}


def read_dxf(dxf_path: str):
    return ezdxf.readfile(dxf_path)


def detect_units(doc, bounds=None):
    insunits = doc.header.get("$INSUNITS")
    if insunits in INSUNITS_SCALE:
        unit_name, scale = INSUNITS_SCALE[insunits]
        return unit_name, scale, "header"

    scale = 1.0
    unit_name = "m"
    if bounds:
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        diag = math.hypot(width, height)
        if diag > 10000:
            unit_name = "mm"
            scale = 0.001
        elif diag > 1000:
            unit_name = "cm"
            scale = 0.01
        else:
            unit_name = "m"
            scale = 1.0
    return unit_name, scale, "heuristic"


def list_layers(doc):
    return [layer.dxf.name for layer in doc.layers]
