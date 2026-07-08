#!/usr/bin/env bash
# Valida a captura nativa. Rode DEPOIS de conceder Gravação de Tela + Microfone.
# Faz 2 passes: (1) mic-only (fale, nada tocando) e (2) sistema (sons tocando).
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$DIR/voxlog-rec.app/Contents/MacOS/voxlog-rec"
[ -x "$BIN" ] || { echo "❌ voxlog-rec ausente — rode: bash $DIR/build.sh"; exit 1; }

run() {  # $1=segundos $2=arquivo_saida — grava PCM e devolve o stderr
  "$BIN" > "$2" 2>/tmp/vox_val.err &
  local pid=$!; sleep "$1"; kill -TERM "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  cat /tmp/vox_val.err
}
level() { ffmpeg -hide_banner -nostats -f f32le -ar 48000 -ac 1 -i "$1" -af astats=metadata=1 -f null - 2>&1 | grep 'RMS level dB' | head -1; }

echo "════ PASSE 1: MIC-ONLY — FALE algo agora por ~5s (nada mais tocando) ════"
ERR="$(run 5 /tmp/vox_mic.f32)"; echo "$ERR"
echo "→ nível mic: $(level /tmp/vox_mic.f32)"
echo "$ERR" | grep -q 'mic=0 ' && echo "❌ MIC não capturou (mic=0) — cheque permissão de Microfone / formato acima" \
                               || echo "✅ mic e sistema fluíram"

echo; echo "════ PASSE 2: SISTEMA — tocando sons de teste ~4s ════"
( for i in 1 2 3 4 5; do afplay /System/Library/Sounds/Ping.aiff; sleep 0.1; done ) &
ERR="$(run 4 /tmp/vox_sys.f32)"; echo "$ERR"
echo "→ nível sistema+mic: $(level /tmp/vox_sys.f32)"

echo; echo "════ TECLAS DE VOLUME ════"
V="$(osascript -e 'output volume of (get volume settings)' 2>/dev/null)"
[ "$V" = "missing value" ] && echo "⚠️  saída ainda em Multi-Output ($V) — troque a saída p/ o dispositivo real" \
                           || echo "✅ volume por teclado OK (output volume = $V)"
rm -f /tmp/vox_mic.f32 /tmp/vox_sys.f32 /tmp/vox_val.err
