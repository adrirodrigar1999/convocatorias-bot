"""Fuentes de convocatorias.

  * BOE (sección II.B) vía su API oficial: módulo boe.
  * Boletines autonómicos, provinciales y webs de empleo: lector genérico (web.py),
    configurado en fuentes.yaml.
"""
import os

import yaml

from . import boe
from .web import Fuente

FUENTES = {"BOE": boe}
RUTA_FUENTES = os.getenv("FUENTES_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "fuentes.yaml"))


def cargar_fuentes(ruta: str = RUTA_FUENTES) -> list[Fuente]:
    with open(ruta, encoding="utf-8") as fh:
        datos = yaml.safe_load(fh) or []
    fuentes, ids = [], set()
    for d in datos:
        if d.get("activa", True) is False:
            continue
        if d["id"] in ids:
            raise ValueError(f"id de fuente repetido: {d['id']}")
        ids.add(d["id"])
        conocidos = {k: d.pop(k) for k in list(d) if k in Fuente.__dataclass_fields__}
        conocidos.pop("activa", None)
        fuentes.append(Fuente(**conocidos, extra=d))
    return fuentes
