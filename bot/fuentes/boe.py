"""Fuente BOE: sección II.B (Oposiciones y concursos) vía la API oficial de datos abiertos.

API: https://www.boe.es/datosabiertos/api/boe/sumario/AAAAMMDD
Cada item trae url_xml con el texto completo de la disposición.
"""
import logging
import time
import xml.etree.ElementTree as ET
from datetime import date

import requests

from ..modelo import Convocatoria

log = logging.getLogger(__name__)

API_SUMARIO = "https://www.boe.es/datosabiertos/api/boe/sumario/{fecha}"
SECCION = "2B"
HEADERS = {
    "Accept": "application/xml",
    "User-Agent": "convocatorias-bot/1.0 (uso personal; avisos de empleo publico)",
}
PAUSA_ENTRE_PETICIONES = 0.5  # segundos, para no cargar el servidor del BOE


class SinBoletin(Exception):
    """No hay BOE ese día (domingos y algunos festivos)."""


def _get(session: requests.Session, url: str, intentos: int = 3) -> requests.Response:
    ultimo_error = None
    for n in range(intentos):
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            ultimo_error = e
            espera = 5 * (n + 1)
            log.warning("Fallo pidiendo %s (%s). Reintento en %ss", url, e, espera)
            time.sleep(espera)
    raise ultimo_error  # type: ignore[misc]


def _texto(nodo: ET.Element | None, etiqueta: str) -> str:
    if nodo is None:
        return ""
    hijo = nodo.find(etiqueta)
    return (hijo.text or "").strip() if hijo is not None else ""


def parsear_sumario(xml_bytes: bytes, fecha: date) -> list[Convocatoria]:
    """Extrae los items de la sección 2B. Los items cuelgan del departamento o de un epígrafe."""
    root = ET.fromstring(xml_bytes)
    codigo = _texto(root.find("status"), "code")
    if codigo and codigo != "200":
        raise SinBoletin(f"status {codigo}")

    resultado: list[Convocatoria] = []
    for seccion in root.iter("seccion"):
        if seccion.get("codigo") != SECCION:
            continue
        for dep in seccion.findall("departamento"):
            nombre_dep = dep.get("nombre", "")
            items = list(dep.findall("item"))
            for epi in dep.findall("epigrafe"):
                items.extend(epi.findall("item"))
            for item in items:
                ident = _texto(item, "identificador")
                if not ident:
                    continue
                resultado.append(Convocatoria(
                    id=ident,
                    fuente="BOE",
                    fecha=fecha,
                    departamento=nombre_dep,
                    titulo=" ".join(_texto(item, "titulo").split()),
                    url=_texto(item, "url_html") or f"https://www.boe.es/diario_boe/txt.php?id={ident}",
                    url_pdf=_texto(item, "url_pdf"),
                    url_xml=_texto(item, "url_xml") or f"https://www.boe.es/diario_boe/xml.php?id={ident}",
                ))
    return resultado


def parsear_documento(xml_bytes: bytes) -> list[str]:
    """Devuelve los párrafos del nodo <texto> de una disposición."""
    root = ET.fromstring(xml_bytes)
    texto = root.find(".//texto")
    if texto is None:
        return []
    parrafos = []
    for p in texto.iter("p"):
        t = " ".join("".join(p.itertext()).split())
        if t:
            parrafos.append(t)
    return parrafos


def obtener(fecha: date, session: requests.Session | None = None) -> list[Convocatoria]:
    """Descarga el sumario del día y el texto de cada convocatoria de la sección II.B."""
    session = session or requests.Session()
    r = _get(session, API_SUMARIO.format(fecha=fecha.strftime("%Y%m%d")))
    if r.status_code == 404:
        raise SinBoletin(fecha.isoformat())
    convocatorias = parsear_sumario(r.content, fecha)
    log.info("BOE %s: %d anuncios en II.B", fecha, len(convocatorias))
    for c in convocatorias:
        time.sleep(PAUSA_ENTRE_PETICIONES)
        try:
            doc = _get(session, c.url_xml)
            if doc.status_code == 200:
                c.parrafos = parsear_documento(doc.content)
        except Exception as e:  # el título sigue sirviendo para clasificar
            log.warning("No se pudo leer el texto de %s: %s", c.id, e)
    return convocatorias
