# Deploy — perfil de voz + diarização (avell)

## A. Token HuggingFace (1x)
1. Crie conta em huggingface.co → Settings → Access Tokens → New token (read).
2. Aceite os termos de `pyannote/speaker-diarization-3.1` e `pyannote/segmentation-3.0`
   (abra as páginas dos modelos e clique em "Agree").

## B. Serviço no avell
```bash
ssh avell_ai_server_tailscale
mkdir -p ~/products/whisperx-service && cd ~/products/whisperx-service
# copie server.py e requirements.txt (rsync do setup/avell/whisperx-service/)
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

## C. Enrollment (gera perfil_eu)
```bash
cd ~/products/whisperx-service
HF_TOKEN=hf_xxx ./.venv/bin/python /caminho/voice_enroll.py   # ~200 áudios seus do WhatsApp
ls ~/.config/voxlog/perfil_eu.npy   # deve existir
```

## D. Subir o serviço
```bash
cp setup/avell/whisperx-service/voice-diarize.service ~/.config/systemd/user/
# edite o HF_TOKEN na unit
systemctl --user daemon-reload && systemctl --user enable --now voice-diarize
curl -sS -F file=@/algum/reuniao.m4a http://localhost:5051/v1/audio/diarize | head -c 300
```

## E. Ligar no voxlog (Mac)
No `~/.config/voxlog/voxlog.toml`:
```toml
[voice]
enabled = true
diarize_endpoint = "https://avell-ai-server.tail99394e.ts.net:5051"   # ou túnel/local
```

## F. Backfill das reuniões passadas
```bash
voxlog voice-backfill   # re-diariza as notas tipo: reuniao com áudio disponível
```

## Verificação
- `voxlog voice-status` mostra enabled + endpoint.
- Uma nota de reunião nova/antiga deve ter a seção "Transcrição (diarizada)" com **Eu** / **Falante 2**.
