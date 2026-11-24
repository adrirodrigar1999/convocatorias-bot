"""Configuración del bot.

Los secretos (token de Telegram, API key opcional) van en variables de entorno
(.env). El perfil (titulación, regiones, grupos) se edita aquí.
"""
import os

# --- Telegram -------------------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Programación -----------------------------------------------------------
# El BOE sale de lunes a sábado sobre las 7:30. Se revisa después.
HORA_EJECUCION = os.getenv("HORA_EJECUCION", "08:30")
ZONA_HORARIA = "Europe/Madrid"
# Mensaje silencioso diario aunque no haya novedades (sirve para saber que el bot sigue vivo)
RESUMEN_DIARIO = os.getenv("RESUMEN_DIARIO", "1") == "1"
# Días hacia atrás que se revisan en la primera ejecución. Solo se avisa de las que siguen con
# plazo abierto (20 días hábiles ≈ 4 semanas, así que 45 cubre de sobra los plazos normales).
DIAS_PRIMERA_EJECUCION = int(os.getenv("DIAS_PRIMERA_EJECUCION", "45"))

DB_PATH = os.getenv("DB_PATH", "data/convocatorias.sqlite")

# --- Perfil ---------------------------------------------------------------------
TITULACIONES = [
    "Grado en Multimedia (UOC)",
    "Máster Universitario en Ingeniería Informática (UOC)",
]

# Regiones donde interesa CUALQUIER plaza accesible con tu titulación.
# Fuera de ellas solo se avisa de plazas de informática.
REGIONES = ["Asturias", "Castilla y León", "Cantabria"]

# Grupos que te interesan en las regiones. None = todos (A1, A2, B, C1, C2, AP).
# Ejemplo para limitar: ["A1", "A2", "B", "C1"]
GRUPOS_REGION = None
# Si no se puede deducir el grupo del texto, ¿avisar igualmente?
INCLUIR_GRUPO_DESCONOCIDO = True

# --- Clasificación con IA (opcional) -------------------------------------------
# Si pones una API key de Anthropic, los casos dudosos ("revisar titulación")
# se los pasa a Claude para afinar la etiqueta. Sin key funciona igual con reglas.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
