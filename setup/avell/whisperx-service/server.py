#!/usr/bin/env python3
"""Serviço de diarização (:5051). POST /v1/audio/diarize file=@audio
-> {language, speakers, text, segments}. Rotula 'Eu' via match com perfil_eu (ECAPA)."""
import json, os, subprocess, tempfile
from pathlib import Path
import numpy as np
import torch, torchaudio, whisperx
from flask import Flask, request, jsonify
from speechbrain.inference.speaker import EncoderClassifier

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
HF_TOKEN = os.environ["HF_TOKEN"]
CFG = Path.home() / ".config/voxlog"
PERFIL = np.load(CFG / "perfil_eu.npy") if (CFG / "perfil_eu.npy").exists() else None
THRESHOLD = (json.loads((CFG / "perfil_eu.json").read_text()).get("threshold", 0.5)
             if (CFG / "perfil_eu.json").exists() else 0.5)

app = Flask(__name__)
_wx = whisperx.load_model(os.environ.get("WX_MODEL", "small"), DEVICE,
                          compute_type="int8", language="pt")
_enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                      run_opts={"device": DEVICE})


def _embed(wav_path, intervals):
    # embeda a fala TODA do falante (concatena os segmentos) — 1 segmento curto
    # de ~1s dá embedding ruidoso e erra o match com o perfil.
    sig, sr = torchaudio.load(wav_path)
    parts = [sig[:, int(a * sr):int(b * sr)] for a, b in intervals if b > a]
    seg = torch.cat(parts, dim=1) if parts else sig
    e = _enc.encode_batch(seg).squeeze().detach().cpu().numpy()
    return e / (np.linalg.norm(e) + 1e-9)


@app.post("/v1/audio/diarize")
def diarize():
    f = request.files["file"]
    with tempfile.TemporaryDirectory() as td:
        # nome fixo (não usar f.filename: evita path traversal a partir do request)
        src = os.path.join(td, "input.m4a"); f.save(src)
        wav = os.path.join(td, "audio.wav")
        # subprocess.run com lista (sem shell) — paths controlados, sem injeção
        subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", wav],
                       capture_output=True, check=True)
        audio = whisperx.load_audio(wav)
        result = _wx.transcribe(audio, batch_size=4)
        align, meta = whisperx.load_align_model(language_code="pt", device=DEVICE)
        result = whisperx.align(result["segments"], align, meta, audio, DEVICE)
        del align, meta                                   # GPU apertada (6GB c/ :5050):
        if DEVICE == "cuda": torch.cuda.empty_cache()     # libera antes da diarização
        diar = whisperx.DiarizationPipeline(use_auth_token=HF_TOKEN, device=DEVICE)
        dseg = diar(audio)
        del diar
        if DEVICE == "cuda": torch.cuda.empty_cache()
        result = whisperx.assign_word_speakers(dseg, result)
        # match cada falante ao perfil_eu
        eu_label = None
        if PERFIL is not None:
            spk_iv = {}
            for s in result["segments"]:
                spk_iv.setdefault(s.get("speaker", "SPEAKER_?"), []).append((s["start"], s["end"]))
            best, best_sim = None, -1.0
            for spk, ivs in spk_iv.items():
                sim = float(np.dot(_embed(wav, ivs), PERFIL))
                if sim > best_sim:
                    best, best_sim = spk, sim
            if best_sim >= THRESHOLD:
                eu_label = best
        # renomeia rótulos
        nomes, n = {}, 2
        for s in result["segments"]:
            spk = s.get("speaker", "SPEAKER_?")
            if spk == eu_label:
                nomes[spk] = "Eu"
            elif spk not in nomes:
                nomes[spk] = f"Falante {n}"; n += 1
        lines, segs = [], []
        for s in result["segments"]:
            spk = nomes.get(s.get("speaker", "SPEAKER_?"), "Falante ?")
            mm = int(s["start"] // 60); ss = int(s["start"] % 60)
            lines.append(f"**{spk}** [{mm:02d}:{ss:02d}]: {s['text'].strip()}")
            segs.append({"speaker": spk, "start": s["start"], "end": s["end"],
                         "text": s["text"].strip()})
    return jsonify({"language": "pt", "speakers": sorted(set(nomes.values())),
                    "text": "\n".join(lines), "segments": segs})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5051)
