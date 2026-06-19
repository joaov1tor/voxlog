#!/usr/bin/env bash
# Uso: record.sh <tipo> <staging_dir>
# Grava o Aggregate Device (mic + sistema) até SIGINT/SIGTERM.
# Imprime o caminho do arquivo .m4a na stdout (1a linha).
set -euo pipefail

# Hammerspoon (hs.task) roda com PATH mínimo — garanta o Homebrew no PATH p/ achar o ffmpeg
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

TIPO="${1:?uso: record.sh <tipo> <staging_dir>}"
STAGING="${2:?uso: record.sh <tipo> <staging_dir>}"
DEVICE_NAME="voxlog-Aggregate"

mkdir -p "$STAGING"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$STAGING/${TS}_${TIPO}.m4a"
echo "$OUT"

# Descobre o índice do device de áudio pelo nome
# `ffmpeg -list_devices` SEMPRE sai com código != 0 (mesmo listando ok); com
# `set -e -o pipefail` isso abortaria o script. O `|| true` blinda a busca.
IDX="$(ffmpeg -f avfoundation -list_devices true -i "" 2>&1 \
  | awk -v name="$DEVICE_NAME" '
      /AVFoundation audio devices/{a=1}
      a && $0 ~ name {line=$0; gsub(/.*\[/,"",line); gsub(/\].*/,"",line); print line; exit}')" || true
: "${IDX:?Aggregate device '$DEVICE_NAME' nao encontrado — rode o setup de audio}"

# -i ":IDX" = sem vídeo, só o device de áudio IDX. AAC 192k.
# -movflags frag_keyframe+empty_moov: MP4 fragmentado → arquivo fica válido
# mesmo se o ffmpeg for encerrado por SIGTERM (como o Hammerspoon faz ao parar).
exec ffmpeg -hide_banner -loglevel warning \
  -f avfoundation -i ":${IDX}" \
  -c:a aac -b:a 192k \
  -movflags +frag_keyframe+empty_moov+default_base_moof \
  -frag_duration 1000000 \
  "$OUT"
