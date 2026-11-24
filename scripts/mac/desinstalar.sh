#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.convocatorias-bot.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Tarea eliminada. Los datos siguen en la carpeta data/ por si vuelves a instalarlo."
