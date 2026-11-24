"""Opcional: afina con Claude las convocatorias marcadas como "revisar titulación".

Solo se usa si hay ANTHROPIC_API_KEY. Si falla, se queda la etiqueta de las reglas.
"""
import json
import logging

import requests

from . import config
from .modelo import Convocatoria, Resultado

log = logging.getLogger(__name__)

PROMPT = """Eres un experto en oposiciones en España. Una persona tiene estas titulaciones:
{titulaciones}

Lee este anuncio oficial y dime si puede presentarse por titulación.
Responde SOLO con JSON: {{"etiqueta": "ok" | "revisar" | "no", "motivo": "<máx. 20 palabras>"}}
- "ok": seguro que su titulación sirve (p. ej. piden cualquier grado o una inferior).
- "no": piden claramente otra titulación concreta que no tiene.
- "revisar": el anuncio no lo deja claro.

Título: {titulo}
Texto:
{texto}
"""


def afinar(c: Convocatoria, r: Resultado) -> Resultado:
    if not config.ANTHROPIC_API_KEY or r.titulacion != "revisar":
        return r
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.ANTHROPIC_MODEL,
                "max_tokens": 200,
                "messages": [{
                    "role": "user",
                    "content": PROMPT.format(
                        titulaciones="\n".join("- " + t for t in config.TITULACIONES),
                        titulo=c.titulo,
                        texto=c.texto[:6000],
                    ),
                }],
            },
            timeout=60,
        )
        resp.raise_for_status()
        salida = resp.json()["content"][0]["text"]
        datos = json.loads(salida[salida.index("{"): salida.rindex("}") + 1])
        if datos.get("etiqueta") in ("ok", "revisar", "no"):
            r.titulacion = datos["etiqueta"]
            r.nota_titulacion = datos.get("motivo", r.nota_titulacion) + " (IA)"
            if r.titulacion == "no" and r.ambito == "region" and not r.informatica:
                r.enviar = False
                r.motivo = "IA: titulación no encaja"
    except Exception as e:
        log.warning("IA no disponible para %s: %s", c.id, e)
    return r
