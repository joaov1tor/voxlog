#!/usr/bin/env bash
# Uso: record.sh <tipo> <staging_dir> [segment_seconds]
# Captura NATIVA (ScreenCaptureKit): áudio do sistema + microfone, mixado em mono.
# Sem BlackHole / sem Multi-Output → a saída de som fica no dispositivo real.
# Imprime o session id (1a linha stdout); grava segmentos .m4a até SIGTERM/SIGINT.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

TIPO="${1:?uso: record.sh <tipo> <staging_dir> [segment_seconds]}"
STAGING="${2:?uso: record.sh <tipo> <staging_dir> [segment_seconds]}"
SEG="${3:-1200}"                        # segundos por segmento (default 20min)

DIR="$(cd "$(dirname "$0")" && pwd)"
REC="$DIR/voxlog-rec.app/Contents/MacOS/voxlog-rec"
LOG="$STAGING/../voxlog-rec.log"
[ -x "$REC" ] || { echo "voxlog-rec ausente — rode recorder/build.sh" >&2; exit 1; }

mkdir -p "$STAGING"
TS="$(date +%Y%m%d-%H%M%S)"
SESSION="${TS}_${TIPO}"
echo "$SESSION"                          # 1a linha stdout = session id (lida pelo Hammerspoon)

# PCM (f32le mono 48k) trafega por um FIFO: recorder → ffmpeg. O FIFO dá PIDs
# explícitos (p/ encaminhar o SIGTERM só ao recorder) e EOF limpo p/ o ffmpeg
# finalizar o último segmento ao parar.
FIFO="$STAGING/.pcm.$$"
mkfifo "$FIFO"
cleanup() { rm -f "$FIFO"; }
trap cleanup EXIT

# ffmpeg: encoda AAC e corta em segmentos (MP4 fragmentado, válido mesmo se cortado)
ffmpeg -hide_banner -loglevel warning \
  -f f32le -ar 48000 -ac 1 -i "$FIFO" \
  -c:a aac -b:a 192k \
  -f segment -segment_time "$SEG" -reset_timestamps 1 \
  -segment_format mp4 -movflags +frag_keyframe+empty_moov+default_base_moof \
  "$STAGING/${SESSION}_%03d.m4a" &
FFPID=$!

"$REC" > "$FIFO" 2>>"$LOG" &
RECPID=$!

# SIGTERM (Hammerspoon ao parar) → encerra o recorder; ele fecha a stdout → ffmpeg
# vê EOF e finaliza o segmento em andamento (sem corromper).
trap 'kill -TERM "$RECPID" 2>/dev/null' TERM INT
wait "$RECPID" 2>/dev/null              # recorder terminou → FIFO fecha
wait "$FFPID"  2>/dev/null              # ffmpeg finaliza
