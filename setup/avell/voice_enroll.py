#!/usr/bin/env python3
"""Gera ~/.config/voxlog/perfil_eu.npy a partir dos áudios is_from_me do WhatsApp.
Roda no avell (GPU). Usa o MESMO modelo de embedding do serviço (ECAPA)."""
import json, os, random, subprocess, sqlite3, tempfile, urllib.request
from pathlib import Path
import numpy as np
import torch
from speechbrain.inference.speaker import EncoderClassifier

DB = "/home/jv/.whatsapp-mcp/whatsapp-bridge/store/messages.db"
BRIDGE = "http://localhost:8085/api/download"
OUT = Path.home() / ".config/voxlog"
N_SAMPLES = 200


def bridge_download(mid, chat):
    data = json.dumps({"message_id": mid, "chat_jid": chat}).encode()
    req = urllib.request.Request(BRIDGE, data=data,
                                 headers={"Content-Type": "application/json"})
    try:                              # falha pontual (ex.: 500 num áudio) não mata o enrollment
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.loads(r.read())
        return res.get("path") if res.get("success") else None
    except Exception:
        return None


def to_wav(src, dst):
    subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", dst],
                   capture_output=True, check=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT id, chat_jid FROM messages WHERE media_type='audio' AND is_from_me=1 "
        "ORDER BY timestamp DESC LIMIT 2000").fetchall()
    con.close()
    random.seed(42); random.shuffle(rows)
    enc = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        run_opts={"device": "cuda" if torch.cuda.is_available() else "cpu"})
    import torchaudio
    embs = []
    for mid, chat in rows:
        if len(embs) >= N_SAMPLES:
            break
        path = bridge_download(mid, chat)
        if not path or not os.path.exists(path):
            continue
        try:
            with tempfile.TemporaryDirectory() as td:
                wav = os.path.join(td, "a.wav"); to_wav(path, wav)
                sig, _ = torchaudio.load(wav)
                e = enc.encode_batch(sig).squeeze().detach().cpu().numpy()
                e = e / (np.linalg.norm(e) + 1e-9)
                embs.append(e)
        except Exception as ex:
            print("skip", mid, ex)
    if not embs:
        raise SystemExit("nenhum embedding gerado")
    centroide = np.mean(np.stack(embs), axis=0)
    centroide = centroide / (np.linalg.norm(centroide) + 1e-9)
    np.save(OUT / "perfil_eu.npy", centroide)
    (OUT / "perfil_eu.json").write_text(json.dumps(
        {"n_samples": len(embs), "model": "speechbrain/spkrec-ecapa-voxceleb",
         "threshold": 0.5}, indent=2))
    print(f"OK: perfil_eu.npy com {len(embs)} amostras")


if __name__ == "__main__":
    main()
