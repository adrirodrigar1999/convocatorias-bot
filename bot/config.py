"""Configuración del bot.

Los secretos (token de Telegram, API key opcional) van en variables de entorno
(.env). El perfil (titulación, regiones, grupos) se edita aquí.
"""
import os


def _cargar_env() -> None:
    """Lee el .env de la raíz del proyecto (en el Mac); en GitHub los secretos llegan como variables."""
    ruta = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding="utf-8") as fh:
        for linea in fh:
            linea = linea.split(" #")[0].strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env()

# --- Telegram -------------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Programación -----------------------------------------------------------
# El BOE sale de lunes a sábado sobre las 7:30. Se revisa después.
HORA_EJECUCION = os.getenv("HORA_EJECUCION", "09:00")
# Modo programado (Mac): días en que toca revisar. Si el Mac está apagado, se hace al encenderlo.
DIAS_EJECUCION = os.getenv("DIAS_EJECUCION", "lun,jue")
ZONA_HORARIA = "Europe/Madrid"
# Mensaje silencioso diario aunque no haya novedades (sirve para saber que el bot sigue vivo)
RESUMEN_DIARIO = os.getenv("RESUMEN_DIARIO", "0") == "1"
# Días hacia atrás que se revisan en la primera ejecución. Solo se avisa de las que siguen con
# plazo abierto (20 días hábiles ≈ 4 semanas, así que 45 cubre de sobra los plazos normales).
DIAS_PRIMERA_EJECUCION = int(os.getenv("DIAS_PRIMERA_EJECUCION", "45"))

_RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.getenv("DB_PATH", os.path.join(_RAIZ, "data", "convocatorias.sqlite"))
ULTIMA_EJECUCION_PATH = os.path.join(os.path.dirname(DB_PATH), "ultima_ejecucion.txt")

# --- Perfil ---------------------------------------------------------------------
TITULACIONES = [
    "Grado en Multimedia (UOC)",
    "Máster Universitario en Ingeniería Informática (UOC)",
]

# Regiones donde, además de informática, interesan plazas de oficina que pidan un grado.
# Fuera de ellas solo se avisa de plazas de informática.
REGIONES = ["Asturias"]

# En esas regiones: solo estos grupos (A1/A2 = piden grado) ...
GRUPOS_REGION = ["A1", "A2"]
# ... y si no se puede deducir el grupo del texto, no se avisa.
INCLUIR_GRUPO_DESCONOCIDO = False
# ... y solo puestos de oficina: administración general, gestión, jurídico, RR. HH., económico, etc.
REGION_SOLO_OFICINA = True

# Una convocatoria parecida a otra ya enviada en estos días se considera repetida
DIAS_ANTIDUPLICADOS = 150

# --- Clasificación con IA (opcional) -------------------------------------------
# Si pones una API key de Anthropic, los casos dudosos ("revisar titulación")
# se los pasa a Claude para afinar la etiqueta. Sin key funciona igual con reglas.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
