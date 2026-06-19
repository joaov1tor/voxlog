#!/usr/bin/env bash
# Uso: record.sh <tipo> <staging_dir>
# Grava o Aggregate Device (mic + sistema) até SIGINT/SIGTERM.
# Imprime o caminho do arquivo .m4a na stdout (1a linha).
set -euo pipefail

TIPO="${1:?uso: record.sh <tipo> <staging_dir>}"
STAGING="${2:?uso: record.sh <tipo> <staging_dir>}"
DEVICE_NAME="voxlog-Aggregate"

mkdir -p "$STAGING"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$STAGING/${TS}_${TIPO}.m4a"
echo "$OUT"

# Descobre o índice do device de áudio pelo nome
IDX="$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
  | awk -v name="$DEVICE_NAME" '/AVFoundation audio devices/{a=1} a && $0 ~ name {match($0,/\[([0-9]+)\]/,m); print m[1]; exit}')"
: "${IDX:?Aggregate device '$DEVICE_NAME' nao encontrado — rode o setup de audio}"

# -i ":IDX" = sem vídeo, só o device de áudio IDX. AAC 192k.
exec ffmpeg -hide_banner -loglevel warning \
  -f avfoundation -i ":${IDX}" \
  -c:a aac -b:a 192k \
  "$OUT"
