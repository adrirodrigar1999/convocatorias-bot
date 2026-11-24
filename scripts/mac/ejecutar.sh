#!/bin/bash
# Lo lanza launchd cada hora. Actualiza el código (por si hay fuentes nuevas) y revisa solo si toca.
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$DIR" || exit 1
mkdir -p logs
{
  echo "----- $(date '+%Y-%m-%d %H:%M') -----"
  git pull --ff-only -q 2>&1 || echo "(sin actualizar el código: $?)"
  if [[ requirements.txt -nt .venv/.instalado ]]; then
    .venv/bin/pip install -q -r requirements.txt && touch .venv/.instalado
  fi
  .venv/bin/python -m bot.main --programado
} >> logs/bot.log 2>&1
# El registro no crece sin límite
tail -n 5000 logs/bot.log > logs/bot.log.tmp && mv logs/bot.log.tmp logs/bot.log
