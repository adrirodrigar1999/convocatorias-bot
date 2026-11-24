"""Formato y envío de avisos por Telegram (Bot API, sin librerías extra)."""
import html
from datetime import date
import logging
import time

import requests

from . import config
from .modelo import Convocatoria, Resultado

log = logging.getLogger(__name__)

ETIQUETA = {
    "ok": "✅ Tu titulación encaja",
    "revisar": "⚠️ Revisa la titulación",
}


def _e(s: str) -> str:
    return html.escape(s, quote=False)


def formatear(c: Convocatoria, r: Resultado) -> str:
    lineas = []
    cabecera = "📍 " + r.region if r.region else "🇪🇸 Toda España"
    if r.informatica:
        cabecera += " · 💻 Informática"
    if r.afin:
        cabecera += " · 🎬 Afín a Multimedia"
    lineas.append(f"<b>{cabecera}</b>")
    lineas.append(f"🏛 {_e(r.organismo)}")

    if r.plazas:
        for p in r.plazas[:6]:
            lineas.append(f"• {_e(p)}")
        if len(r.plazas) > 6:
            lineas.append(f"• … y {len(r.plazas) - 6} plazas más")
    else:
        lineas.append(f"📝 {_e(c.titulo)}")

    detalle = []
    if r.grupos:
        detalle.append("Grupo " + "/".join(r.grupos))
    if r.sistema:
        detalle.append(r.sistema)
    if r.turno:
        detalle.append("turno " + r.turno.lower())
    if detalle:
        lineas.append("🎯 " + " · ".join(detalle))

    lineas.append(f"{ETIQUETA.get(r.titulacion, '')} — {_e(r.nota_titulacion)}")

    if r.plazo_fin:
        quedan = (r.plazo_fin - date.today()).days
        resto = "último día" if quedan == 0 else f"quedan {quedan} días"
        lineas.append(f"🟢 Plazo abierto: {r.plazo_texto} → hasta el <b>{r.plazo_fin:%d/%m/%Y}</b> "
                      f"(aprox., {resto})")
    elif r.plazo_texto:
        lineas.append(f"⏳ {_e(r.plazo_texto)}")
    if r.bases:
        lineas.append(f"📄 Bases: {_e(r.bases)}")
    if c.fuente == "BOE":
        lineas.append(f'🔗 <a href="{html.escape(c.url)}">{c.id}</a> (BOE, {c.fecha:%d/%m/%Y})')
    else:
        lineas.append(f'🔗 <a href="{html.escape(c.url)}">Ver anuncio</a> ({_e(c.fuente)}, visto el {c.fecha:%d/%m/%Y})')
    return "\n".join(lineas)


def enviar(texto: str, silencioso: bool = False) -> bool:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID; mensaje no enviado:\n%s", texto)
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    datos = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": silencioso,
    }
    for intento in range(3):
        r = requests.post(url, data=datos, timeout=30)
        if r.status_code == 429:  # límite de Telegram
            espera = r.json().get("parameters", {}).get("retry_after", 5)
            time.sleep(espera + 1)
            continue
        if r.ok:
            time.sleep(1.1)  # máx. ~1 mensaje/segundo por chat
            return True
        log.error("Telegram respondió %s: %s", r.status_code, r.text)
        return False
    return False


def formatear_resumen(nombre: str, pares: list) -> str:
    """Primera pasada de una fuente: un único mensaje con lo que ya estaba publicado."""
    lineas = [f"🗂 <b>{_e(nombre)}</b>: primera revisión, {len(pares)} anuncios que pueden interesarte "
              "(algunos pueden estar ya cerrados):"]
    for c, r in pares[:15]:
        marca = "💻 " if r.informatica else ""
        texto = c.titulo if len(c.titulo) <= 160 else c.titulo[:157] + "…"
        lineas.append(f'• {marca}<a href="{html.escape(c.url)}">{_e(texto)}</a>')
    if len(pares) > 15:
        lineas.append(f"… y {len(pares) - 15} más")
    return "\n".join(lineas)
