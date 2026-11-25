"""Seguimiento de procesos selectivos a los que te has presentado (seguimiento.yaml).

Una vez al día mira los boletines y tablones indicados y avisa de cualquier anuncio nuevo del proceso:
lista de admitidos, tribunal, fecha de examen, notas, bolsa... Todo lo que la búsqueda de convocatorias
descarta a propósito porque no abre plazo.
"""
import html
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

import requests
import yaml

from . import telegram
from .fuentes import cargar_fuentes, web
from .modelo import Convocatoria

log = logging.getLogger(__name__)
RUTA = os.getenv("SEGUIMIENTO_PATH", os.path.join(os.path.dirname(__file__), "..", "seguimiento.yaml"))
NO_SEGUIR = r"(?!)"   # patrón que nunca casa: las URLs sueltas se leen tal cual, sin saltar a otras páginas


@dataclass
class Proceso:
    id: str
    nombre: str
    buscar: re.Pattern
    excluir: re.Pattern | None = None
    hasta: date | None = None
    fuentes: list = field(default_factory=list)
    urls: list = field(default_factory=list)


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return " ".join("".join(ch for ch in s if not unicodedata.combining(ch)).split())


def cargar(ruta: str = RUTA) -> list[Proceso]:
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8") as fh:
        datos = yaml.safe_load(fh) or []
    procesos = []
    for d in datos:
        hasta = d.get("hasta")
        procesos.append(Proceso(
            id=d["id"], nombre=d["nombre"], buscar=re.compile(d["buscar"], re.I),
            excluir=re.compile(d["excluir"], re.I) if d.get("excluir") else None,
            hasta=date.fromisoformat(str(hasta)) if hasta else None,
            fuentes=list(d.get("fuentes") or []), urls=list(d.get("urls") or []),
        ))
    return procesos


def coincide(p: Proceso, texto: str) -> bool:
    t = normalizar(texto)
    return bool(p.buscar.search(t)) and not (p.excluir and p.excluir.search(t))


def _fuentes_de(p: Proceso, catalogo: dict) -> list[web.Fuente]:
    fuentes = []
    for fid in p.fuentes:
        if fid in catalogo:
            fuentes.append(catalogo[fid])
        else:
            log.warning("Seguimiento %s: la fuente %s no está en fuentes.yaml", p.id, fid)
    for i, url in enumerate(p.urls):
        fuentes.append(web.Fuente(id=f"{p.id}-url{i}", nombre=url.split("/")[2], tipo="web", url=url,
                                  seguir=NO_SEGUIR, pdf=False))
    return fuentes


def formatear(p: Proceso, f: web.Fuente, it: web.Item, hoy: date) -> str:
    return (f"📌 <b>Novedad en tu proceso</b>: {html.escape(p.nombre, quote=False)}\n\n"
            f"{html.escape(it.texto[:600], quote=False)}\n\n"
            f'🔗 <a href="{html.escape(it.url)}">Ver anuncio</a> ({html.escape(f.nombre, quote=False)}, '
            f"visto el {hoy:%d/%m/%Y})")


def revisar(store, hoy: date, dry_run: bool = False, procesos: list[Proceso] | None = None) -> int:
    """Devuelve cuántos avisos ha mandado (o mostrado, en dry_run)."""
    procesos = [p for p in (procesos if procesos is not None else cargar()) if not p.hasta or p.hasta >= hoy]
    if not procesos:
        return 0
    catalogo = {f.id: f for f in cargar_fuentes()}
    avisos = 0
    for p in procesos:
        for f in _fuentes_de(p, catalogo):
            try:
                items, _ = web.obtener_crudo(f, requests.Session(), hoy)
            except Exception as e:
                log.warning("Seguimiento %s: %s no responde (%s)", p.id, f.id, e)
                continue
            vistos = set()
            for it in items:
                texto = " ".join(it.texto.split())
                if it.nav or len(texto) < 15 or not coincide(p, texto):
                    continue
                ident = f"seg:{p.id}:{web.Item(texto, it.url).clave}"
                if ident in vistos or (store and store.visto(ident)):
                    continue
                vistos.add(ident)
                it.texto = texto
                mensaje = formatear(p, f, it, hoy)
                if dry_run:
                    print("\n" + "=" * 70 + "\n" + mensaje)
                    avisos += 1
                    continue
                if telegram.enviar(mensaje):
                    store.guardar(Convocatoria(id=ident, fuente=f.nombre, fecha=hoy, departamento=p.nombre,
                                               titulo=texto, url=it.url), True, "seguimiento")
                    avisos += 1
    log.info("Seguimiento: %d avisos", avisos)
    return avisos
