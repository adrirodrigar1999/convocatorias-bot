#!/bin/bash
# Instala el bot en el Mac: entorno de Python + tarea de launchd que comprueba cada hora si toca revisar.
set -euo pipefail
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$DIR"

case "$DIR" in
  "$HOME/Documents"*|"$HOME/Desktop"*|"$HOME/Downloads"*|*"Mobile Documents"*)
    echo "⚠️  Mueve la carpeta fuera de Documentos/Escritorio/Descargas/iCloud (p. ej. a ~/convocatorias-bot):"
    echo "    macOS no deja que las tareas en segundo plano lean esas carpetas."
    exit 1;;
esac

if [[ ! -f .env ]]; then
  echo "Falta el fichero .env. Haz: cp .env.example .env  y pon TELEGRAM_TOKEN y TELEGRAM_CHAT_ID."
  exit 1
fi

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    PY="$(command -v "$c")"; break
  fi
done
if [[ -z "$PY" ]]; then
  echo "Necesitas Python 3.10 o superior:  brew install python@3.12"
  exit 1
fi
echo "Usando $PY"

"$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
mkdir -p data logs
touch .venv/.instalado

if [[ "${1:-}" == "--reset" ]]; then
  echo "Borrando los avisos anteriores del chat y el estado del bot…"
  .venv/bin/python -m bot.main --reset --si
fi

PLIST="$HOME/Library/LaunchAgents/com.convocatorias-bot.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__DIR__#$DIR#g" scripts/mac/com.convocatorias-bot.plist > "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "✅ Instalado. La primera revisión ya está en marcha (mira logs/bot.log)."
echo "   A partir de ahora: Comprobará cada hora (y al iniciar sesión) si ha pasado un lunes o jueves desde la última revisión."
echo "   Registro: $DIR/logs/bot.log"
echo "   Prueba de Telegram:  .venv/bin/python -m bot.main --prueba-telegram"
