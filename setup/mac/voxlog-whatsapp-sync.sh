#!/bin/bash
# Sincroniza as notas de WhatsApp do avell para o cofre do Mac (one-way: avell -> Mac).
# Roda via launchd (com.voxlog.whatsapp-sync) a cada 30 min. O avell é a "extensão"
# de processamento; o cofre do Mac é o destino. NÃO é bidirecional — só puxa.
set -euo pipefail
RCLONE="$(command -v rclone || echo /opt/homebrew/bin/rclone)"
SRC="avell:obsidian-vault/SecundBrain/🎙️ WhatsApp"
DST="/Volumes/SSD/Dropbox/obsidian/SecundBrain/🎙️ WhatsApp"
LOG="$HOME/Library/Logs/voxlog-whatsapp-sync.log"

# só roda se o destino (SSD/cofre) estiver montado
[ -d "$(dirname "$DST")" ] || { echo "$(date '+%F %T') destino indisponível, pulei" >> "$LOG"; exit 0; }

"$RCLONE" copy "$SRC" "$DST" --log-file "$LOG" --log-level INFO --stats-one-line
echo "$(date '+%F %T') sync ok" >> "$LOG"
