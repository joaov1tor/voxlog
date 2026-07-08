# voxlog — Perfil de voz + diarização (Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **LOCAL-ONLY** — não empurrar pro voxlog público (referencia áudios do WhatsApp + infra avell).

**Goal:** Identificar "Eu" (e separar os demais falantes) nas transcrições de **reunião** do voxlog, via um perfil de voz do usuário (enrollment automático dos áudios do WhatsApp) + diarização (WhisperX/pyannote) rodando no avell, com backfill das reuniões já gravadas.

**Architecture:** Um **serviço de diarização no avell** (`:5051`, WhisperX+pyannote) recebe um áudio e devolve a transcrição já rotulada (`Eu` / `Falante 2…`), casando cada falante com o `perfil_eu` (embedding ECAPA). O pacote `voxlog` (cliente) só envia o áudio e recebe o texto. Como reuniões são **segmentadas**, o cliente **concatena os segmentos** num único arquivo antes de diarizar (rótulo de falante consistente; "Eu" é global pelo match com o perfil). Backfill re-diariza os `.m4a` já salvos e troca a seção de transcrição da nota.

**Tech Stack:** Python 3.11+ (stdlib: `urllib`/`subprocess`/`tempfile`/`re`), pytest com injeção de dependência (`curl=`, `runner=`). No avell: WhisperX, pyannote.audio, SpeechBrain (ECAPA), torch/CUDA, ffmpeg, um serviço HTTP (Flask/FastAPI no estilo do `whisper-service` atual).

## Global Constraints

- **Sem novas dependências no pacote voxlog (cliente).** Só stdlib; HTTP via `subprocess`/`curl` no mesmo padrão de `transcribe.py`. As libs pesadas (whisperx/pyannote/torch) ficam **só no avell**, fora do pacote.
- **Diarização só em reunião** (`tipo == "reuniao"`). Nota de voz (`tipo == "nota"`), WhatsApp e Discord nunca diarizam.
- **Fallback nunca quebra:** se o `:5051` ou o `perfil_eu` faltar, cai para o `:5050` normal (transcrição sem rótulo).
- **Mesmo modelo de embedding** (SpeechBrain ECAPA `speechbrain/spkrec-ecapa-voxceleb`) no enrollment e no serviço — senão os vetores não comparam.
- **Áudio inteiro:** diarizar o áudio combinado da reunião, não por segmento (rótulos consistentes).
- **Idempotente:** backfill pula nota já diarizada (marcada com `diarizado: true` no frontmatter).
- **Token HF** e `perfil_eu.npy` ficam em `~/.config/voxlog/` no avell, **não versionados**.
- Português nas notas/seções. Commits estilo repo (`feat:`/`docs:` + rodapé Co-Authored-By). **Não pushar.**

---

## File Structure

| Arquivo | Responsabilidade |
|---|---|
| `src/voxlog/config.py` (mod) | Seção `[voice]`: `voice_enabled`, `voice_diarize_endpoint`. |
| `src/voxlog/transcribe.py` (mod) | `transcribe_diarized(audio, cfg, curl=None) -> str` — POST do áudio ao `:5051`, devolve o texto rotulado. |
| `src/voxlog/audioutil.py` (novo) | `combine_segments(segs, dest, runner=None) -> Path` — concat ffmpeg dos segmentos num `.m4a` único. |
| `src/voxlog/session.py` (mod) | Em reunião + `voice_enabled`: combina segmentos → diariza → `summarize` do texto inteiro. |
| `src/voxlog/voice_backfill.py` (novo) | Itera notas `tipo: reuniao`, acha o áudio, diariza, troca a seção "Transcrição completa", marca `diarizado: true`. |
| `src/voxlog/cli.py` (mod) | `voxlog voice-backfill [--since] [--config]` e `voxlog voice-status [--config]`. |
| `tests/test_transcribe_diarized.py` (novo) | Testa o cliente HTTP de diarização. |
| `tests/test_audioutil.py` (novo) | Testa o concat de segmentos. |
| `tests/test_session_diariza.py` (novo) | Testa o roteamento de reunião p/ diarização. |
| `tests/test_voice_backfill.py` (novo) | Testa o backfill (troca de seção, idempotência). |
| `tests/test_config.py` (mod) | Testa parse da seção `[voice]`. |
| `setup/avell/whisperx-service/server.py` (novo) | Serviço HTTP `:5051` (WhisperX + match perfil → texto rotulado). |
| `setup/avell/whisperx-service/requirements.txt` (novo) | torch/whisperx/pyannote/speechbrain pinados. |
| `setup/avell/voice_enroll.py` (novo) | Gera `perfil_eu.npy` dos áudios `is_from_me` do WhatsApp. |
| `docs/voz-deploy.md` (novo) | Runbook: HF token, deploy do serviço, enrollment, systemd. |

**Contrato do serviço `:5051`** (todas as tasks do cliente dependem dele):
`POST {endpoint}/v1/audio/diarize` multipart `file=@audio.m4a` →
`200 {"language":"pt","speakers":["Eu","Falante 2"],"text":"**Eu** [00:03]: ...\n**Falante 2** [00:11]: ...","segments":[{"speaker":"Eu","start":3.1,"end":9.4,"text":"..."}]}`.
Em falha/sem perfil → erro HTTP (o cliente faz fallback).

---

## Task 1: Config — seção `[voice]`

**Files:**
- Modify: `src/voxlog/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.voice_enabled: bool = False`, `Config.voice_diarize_endpoint: str = "http://localhost:5051"`. `load_config` lê a tabela `[voice]` com chaves `enabled`, `diarize_endpoint`.

- [ ] **Step 1: Write the failing test** — adicionar a `tests/test_config.py`:

```python
def test_load_config_secao_voice(tmp_path):
    cfg_file = tmp_path / "voxlog.toml"
    cfg_file.write_text(
        'vault_path = "/tmp/v"\n\n[voice]\nenabled = true\n'
        'diarize_endpoint = "http://localhost:5051"\n')
    cfg = load_config(cfg_file)
    assert cfg.voice_enabled is True
    assert cfg.voice_diarize_endpoint == "http://localhost:5051"


def test_load_config_voice_defaults(tmp_path):
    cfg_file = tmp_path / "voxlog.toml"
    cfg_file.write_text('vault_path = "/tmp/v"\n')
    cfg = load_config(cfg_file)
    assert cfg.voice_enabled is False
    assert cfg.voice_diarize_endpoint == "http://localhost:5051"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_config.py -k voice -q`
Expected: FAIL com `AttributeError: ... 'voice_enabled'`.

- [ ] **Step 3: Add fields to `Config`** — em `src/voxlog/config.py`, após `whatsapp_exclude_chats`:

```python
    voice_enabled: bool = False
    voice_diarize_endpoint: str = "http://localhost:5051"
```

- [ ] **Step 4: Parse `[voice]` em `load_config`** — antes do `return cfg`:

```python
    voice = data.get("voice", {})
    if "enabled" in voice:
        cfg.voice_enabled = bool(voice["enabled"])
    if "diarize_endpoint" in voice:
        cfg.voice_diarize_endpoint = voice["diarize_endpoint"]
```

- [ ] **Step 5: Run tests** — `./.venv/bin/python -m pytest tests/test_config.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/voxlog/config.py tests/test_config.py
git commit -m "feat(voz): seção [voice] no config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Cliente HTTP de diarização — `transcribe_diarized`

**Files:**
- Modify: `src/voxlog/transcribe.py`
- Test: `tests/test_transcribe_diarized.py`

**Interfaces:**
- Consumes: `Config` (Task 1).
- Produces: `transcribe_diarized(audio_path: Path, cfg: Config, curl=None) -> str`. Faz `POST {cfg.voice_diarize_endpoint}/v1/audio/diarize` (multipart `file=@audio`) e devolve o campo `text` do JSON. `curl` é um runner injetável `(cmd: list[str]) -> str` (default = `_default_curl`, que já existe em `transcribe.py`).

- [ ] **Step 1: Write the failing test** — criar `tests/test_transcribe_diarized.py`:

```python
from pathlib import Path
from voxlog.config import Config
from voxlog.transcribe import transcribe_diarized


def test_transcribe_diarized_monta_url_e_extrai_text(tmp_path):
    audio = tmp_path / "reuniao.m4a"; audio.write_bytes(b"X")
    cfg = Config(voice_diarize_endpoint="http://localhost:5051")
    captured = {}
    def fake_curl(cmd):
        captured["cmd"] = cmd
        return '{"language":"pt","speakers":["Eu","Falante 2"],"text":"**Eu** [00:03]: oi\\n**Falante 2** [00:11]: ola","segments":[]}'
    out = transcribe_diarized(audio, cfg, curl=fake_curl)
    assert out == "**Eu** [00:03]: oi\n**Falante 2** [00:11]: ola"
    assert "http://localhost:5051/v1/audio/diarize" in captured["cmd"]
    assert f"file=@{audio}" in captured["cmd"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_transcribe_diarized.py -q`
Expected: FAIL com `ImportError: cannot import name 'transcribe_diarized'`.

- [ ] **Step 3: Implement** — adicionar a `src/voxlog/transcribe.py` (reusa `_default_curl` e `import json` já presentes):

```python
def transcribe_diarized(audio_path: Path, cfg: Config, curl=None) -> str:
    run = curl or _default_curl
    url = cfg.voice_diarize_endpoint.rstrip("/") + "/v1/audio/diarize"
    out = run([
        "curl", "-sS", "--fail", "--max-time", "1200", url,
        "-F", f"file=@{audio_path}",
        "-F", "response_format=json",
    ])
    return str(json.loads(out)["text"]).strip()
```

- [ ] **Step 4: Run tests** — `./.venv/bin/python -m pytest tests/test_transcribe_diarized.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/voxlog/transcribe.py tests/test_transcribe_diarized.py
git commit -m "feat(voz): cliente HTTP de diarização (transcribe_diarized)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Concat de segmentos — `combine_segments`

**Files:**
- Create: `src/voxlog/audioutil.py`
- Test: `tests/test_audioutil.py`

**Interfaces:**
- Produces: `combine_segments(segs: list[Path], dest: Path, runner=None) -> Path`. Concatena os `.m4a` (em ordem) num único arquivo `dest` via ffmpeg **concat demuxer** (`-f concat -safe 0 -i lista.txt -c copy dest`). `runner` é injetável `(cmd: list[str]) -> None`. Se houver só 1 segmento, copia direto. Retorna `dest`.

- [ ] **Step 1: Write the failing test** — criar `tests/test_audioutil.py`:

```python
from pathlib import Path
from voxlog.audioutil import combine_segments


def test_combine_segments_monta_concat_ffmpeg(tmp_path):
    s1 = tmp_path / "a_1.m4a"; s1.write_bytes(b"1")
    s2 = tmp_path / "a_2.m4a"; s2.write_bytes(b"2")
    dest = tmp_path / "full.m4a"
    cmds = []
    def runner(cmd):
        cmds.append(cmd)
        dest.write_bytes(b"FULL")   # simula o ffmpeg gerando o arquivo
    out = combine_segments([s1, s2], dest, runner=runner)
    assert out == dest and dest.exists()
    flat = " ".join(cmds[0])
    assert "ffmpeg" in flat and "concat" in flat and str(dest) in flat


def test_combine_segments_um_segmento_copia(tmp_path):
    s1 = tmp_path / "a_1.m4a"; s1.write_bytes(b"SO")
    dest = tmp_path / "full.m4a"
    out = combine_segments([s1], dest)   # sem runner: 1 seg = cópia, não chama ffmpeg
    assert out == dest and dest.read_bytes() == b"SO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_audioutil.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'voxlog.audioutil'`.

- [ ] **Step 3: Implement** — criar `src/voxlog/audioutil.py`:

```python
from __future__ import annotations
import shutil
import subprocess
import tempfile
from pathlib import Path


def _default_runner(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {proc.stderr[:300]}")


def combine_segments(segs: list[Path], dest: Path, runner=None) -> Path:
    segs = [Path(s) for s in segs]
    if len(segs) == 1:
        shutil.copyfile(segs[0], dest)
        return dest
    run = runner or _default_runner
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for s in segs:
            f.write(f"file '{s.resolve()}'\n")
        listfile = f.name
    try:
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", str(dest)])
    finally:
        Path(listfile).unlink(missing_ok=True)
    return dest
```

- [ ] **Step 4: Run tests** — `./.venv/bin/python -m pytest tests/test_audioutil.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/voxlog/audioutil.py tests/test_audioutil.py
git commit -m "feat(voz): combine_segments (concat ffmpeg dos segmentos da reunião)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Roteamento de reunião → diarização em `process_session`

**Files:**
- Modify: `src/voxlog/session.py`
- Test: `tests/test_session_diariza.py`

**Interfaces:**
- Consumes: `combine_segments` (Task 3), `transcribe_diarized` (Task 2), `summarize` (existe), `Config.voice_enabled`.
- Produces: comportamento — quando `tipo == "reuniao"` e `cfg.voice_enabled`, `process_session` **concatena** os segmentos, chama `transcribe_diarized` no áudio inteiro e usa `summarize(texto_inteiro, cfg)` (em vez de transcrever por segmento + `summarize_segments`). Mantém os parâmetros injetáveis (`_transcribe`, `_summarize`, `_duration`) e adiciona `_diarize=None`, `_combine=None` para teste. Caminho não-voz fica idêntico ao atual.

- [ ] **Step 1: Write the failing test** — criar `tests/test_session_diariza.py`:

```python
from pathlib import Path
from voxlog.config import Config
from voxlog.summarize import Summary
from voxlog.session import process_session


def _segs(staging, sid, n):
    for i in range(1, n + 1):
        (staging / f"{sid}_{i}.m4a").write_bytes(b"A" * 1000)


def test_process_session_reuniao_voz_diariza(tmp_path):
    staging = tmp_path / "stg"; staging.mkdir()
    sid = "20260620-140000_reuniao"
    _segs(staging, sid, 2)
    cfg = Config(vault_path=tmp_path / "vault", voice_enabled=True,
                 gravacoes_dir="G", audios_dir="G/_audios")
    combinados = {}
    def fake_combine(segs, dest, runner=None):
        combinados["n"] = len(segs); dest.write_bytes(b"FULL"); return dest
    def fake_diarize(audio, cfg, **kw):
        return "**Eu** [00:03]: oi\n**Falante 2** [00:10]: ola"
    inputs = []
    def fake_summarize(text, cfg, *a, **k):
        inputs.append(text)
        return Summary(resumo="r", assunto="Reunião X", resumido_por="codex")
    note = process_session(str(staging), sid, "reuniao", "Discord", cfg,
                           _duration=lambda p: 120.0,
                           _combine=fake_combine, _diarize=fake_diarize,
                           _summarize=fake_summarize)
    assert combinados["n"] == 2                       # concatenou os 2 segmentos
    txt = note.read_text(encoding="utf-8")
    assert "**Eu** [00:03]: oi" in txt                # transcrição diarizada na nota
    assert any("Falante 2" in t for t in inputs)      # resumo recebeu o texto inteiro
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_session_diariza.py -q`
Expected: FAIL com `TypeError: process_session() got an unexpected keyword argument '_combine'`.

- [ ] **Step 3: Implement** — em `src/voxlog/session.py`, adicionar imports no topo:

```python
import tempfile
from .transcribe import transcribe_diarized as _do_diarize
from .summarize import summarize as _do_summarize
from .audioutil import combine_segments as _do_combine
```

E na assinatura de `process_session`, adicionar os parâmetros injetáveis:

```python
def process_session(staging_dir, session_id, tipo, origem, cfg: Config,
                    force_local: bool = False, *, _transcribe=None,
                    _summarize=None, _duration=None, _diarize=None,
                    _combine=None) -> Path | None:
```

Substituir o bloco que hoje faz `transcripts = [tr(s, cfg) for s in segs]` ... `summary = (_summarize or _do_summarize_segments)(...)` por:

```python
    if tipo == "reuniao" and cfg.voice_enabled:
        combine = _combine or _do_combine
        diarize = _diarize or _do_diarize
        summarize = _summarize or _do_summarize
        with tempfile.TemporaryDirectory() as td:
            full_audio = combine(segs, Path(td) / f"{session_id}.m4a")
            try:
                full = diarize(full_audio, cfg)
            except Exception:
                # fallback: transcrição normal por segmento, sem diarização
                tr = _transcribe or _do_transcribe
                full = "\n".join(tr(s, cfg) for s in segs)
        summary = summarize(full, cfg, force_local)
    else:
        tr = _transcribe or _do_transcribe
        transcripts = [tr(s, cfg) for s in segs]
        full = "\n".join(transcripts)
        summary = (_summarize or _do_summarize_segments)(transcripts, cfg, force_local)
```

(O restante de `process_session` — montar `meta`, `write_note(cfg, meta, summary, full, segs[0])`, mover `segs[1:]` — fica igual.)

- [ ] **Step 4: Run tests** — `./.venv/bin/python -m pytest tests/test_session_diariza.py tests/test_session.py -q` → PASS (inclui o teste pré-existente de sessão).

- [ ] **Step 5: Commit**

```bash
git add src/voxlog/session.py tests/test_session_diariza.py
git commit -m "feat(voz): process_session diariza reunião (combina segmentos + match Eu)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Backfill — `voice_backfill`

**Files:**
- Create: `src/voxlog/voice_backfill.py`
- Test: `tests/test_voice_backfill.py`

**Interfaces:**
- Consumes: `Config`, `transcribe_diarized` (Task 2).
- Produces:
  - `find_meeting_notes(cfg) -> list[Path]` — notas `.md` com `tipo: reuniao` no frontmatter, dentro de `vault_path/gravacoes_dir`.
  - `note_audio_path(cfg, note_path) -> Path | None` — lê `audio: "[[<filename>]]"` do frontmatter e devolve `vault_path/audios_dir/<filename>` se existir.
  - `replace_transcript(md: str, diarized: str) -> str` — troca o conteúdo da seção `## 📝 Transcrição completa` pela versão diarizada (callout `> [!quote]- Transcrição (diarizada)`), e marca `diarizado: true` no frontmatter.
  - `is_diarized(md: str) -> bool` — `True` se o frontmatter tem `diarizado: true`.
  - `backfill(cfg, *, _diarize=None) -> list[Path]` — para cada nota de reunião não-diarizada com áudio disponível, diariza e regrava. Retorna as notas atualizadas. Pula as já diarizadas (idempotente) e as sem áudio.

- [ ] **Step 1: Write the failing test** — criar `tests/test_voice_backfill.py`:

```python
from pathlib import Path
from voxlog.config import Config
from voxlog.voice_backfill import (find_meeting_notes, note_audio_path,
                                   replace_transcript, is_diarized, backfill)

NOTE = """---
tipo: reuniao
data: 2026-06-20
audio: "[[2026-06-20 1400 reuniao.m4a]]"
---

## 📌 Resumo

resumo aqui

## 📝 Transcrição completa

> [!quote]- Transcrição
> tudo misturado sem rótulo
"""


def _setup(tmp_path):
    cfg = Config(vault_path=tmp_path / "v", gravacoes_dir="G", audios_dir="G/_audios")
    folder = cfg.vault_path / "G" / "2026" / "06-Junho"
    folder.mkdir(parents=True)
    note = folder / "2026-06-20 1400 — Reunião — X.md"
    note.write_text(NOTE, encoding="utf-8")
    audios = cfg.vault_path / "G/_audios"; audios.mkdir(parents=True)
    (audios / "2026-06-20 1400 reuniao.m4a").write_bytes(b"A")
    return cfg, note


def test_find_e_audio(tmp_path):
    cfg, note = _setup(tmp_path)
    notes = find_meeting_notes(cfg)
    assert note in notes
    assert note_audio_path(cfg, note).name == "2026-06-20 1400 reuniao.m4a"


def test_replace_transcript_e_marca(tmp_path):
    novo = replace_transcript(NOTE, "**Eu** [00:01]: oi")
    assert "diarizado: true" in novo
    assert "Transcrição (diarizada)" in novo
    assert "**Eu** [00:01]: oi" in novo
    assert "tudo misturado sem rótulo" not in novo
    assert is_diarized(novo) is True


def test_backfill_diariza_e_idempotente(tmp_path):
    cfg, note = _setup(tmp_path)
    chamadas = []
    def fake_diarize(audio, cfg, **kw):
        chamadas.append(Path(audio).name)
        return "**Eu** [00:01]: oi\n**Falante 2** [00:05]: ola"
    out = backfill(cfg, _diarize=fake_diarize)
    assert out == [note]
    assert "**Eu** [00:01]: oi" in note.read_text(encoding="utf-8")
    # 2ª passada: já diarizada -> não chama de novo
    out2 = backfill(cfg, _diarize=fake_diarize)
    assert out2 == []
    assert len(chamadas) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_voice_backfill.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'voxlog.voice_backfill'`.

- [ ] **Step 3: Implement** — criar `src/voxlog/voice_backfill.py`:

```python
from __future__ import annotations
import re
from pathlib import Path
from .config import Config
from .transcribe import transcribe_diarized as _do_diarize


def find_meeting_notes(cfg: Config) -> list[Path]:
    base = cfg.vault_path / cfg.gravacoes_dir
    out = []
    if not base.exists():
        return out
    for md in base.rglob("*.md"):
        head = md.read_text(encoding="utf-8")[:400]
        if re.search(r"^tipo:\s*reuniao\s*$", head, re.MULTILINE):
            out.append(md)
    return sorted(out)


def note_audio_path(cfg: Config, note_path: Path) -> Path | None:
    md = note_path.read_text(encoding="utf-8")
    m = re.search(r'^audio:\s*"\[\[(.+?)\]\]"', md, re.MULTILINE)
    if not m:
        return None
    p = cfg.vault_path / cfg.audios_dir / m.group(1)
    return p if p.exists() else None


def is_diarized(md: str) -> bool:
    return re.search(r"^diarizado:\s*true\s*$", md, re.MULTILINE) is not None


def replace_transcript(md: str, diarized: str) -> str:
    bloco = ("## 📝 Transcrição completa\n\n"
             "> [!quote]- Transcrição (diarizada)\n"
             + "\n".join(f"> {ln}" for ln in diarized.splitlines() or [""]) + "\n")
    # troca tudo a partir do header de transcrição até o fim
    md = re.sub(r"## 📝 Transcrição completa.*\Z", bloco, md, flags=re.DOTALL)
    # marca diarizado: true no frontmatter (após a linha tipo:)
    if not is_diarized(md):
        md = re.sub(r"(^tipo:\s*reuniao\s*$)", r"\1\ndiarizado: true",
                    md, count=1, flags=re.MULTILINE)
    return md


def backfill(cfg: Config, *, _diarize=None) -> list[Path]:
    diarize = _diarize or _do_diarize
    atualizadas = []
    for note in find_meeting_notes(cfg):
        md = note.read_text(encoding="utf-8")
        if is_diarized(md):
            continue
        audio = note_audio_path(cfg, note)
        if audio is None:
            continue
        try:
            diarized = diarize(audio, cfg)
        except Exception:
            continue
        note.write_text(replace_transcript(md, diarized), encoding="utf-8")
        atualizadas.append(note)
    return atualizadas
```

- [ ] **Step 4: Run tests** — `./.venv/bin/python -m pytest tests/test_voice_backfill.py -q` → PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add src/voxlog/voice_backfill.py tests/test_voice_backfill.py
git commit -m "feat(voz): backfill re-diariza reuniões passadas (idempotente)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: CLI — `voice-backfill` e `voice-status`

**Files:**
- Modify: `src/voxlog/cli.py`
- Test: `tests/test_voice_backfill.py` (adiciona teste de CLI)

**Interfaces:**
- Consumes: `voice_backfill.backfill`, `load_config`.
- Produces: subcomandos `voxlog voice-backfill [--config]` (chama `backfill`, imprime nº de notas atualizadas) e `voxlog voice-status [--config]` (imprime se `voice_enabled` e o `diarize_endpoint`).

- [ ] **Step 1: Write the failing test** — adicionar a `tests/test_voice_backfill.py`:

```python
def test_cli_voice_backfill(tmp_path, monkeypatch, capsys):
    import voxlog.cli as cli
    cfg_file = tmp_path / "voxlog.toml"
    cfg_file.write_text(f'vault_path = "{tmp_path}/v"\n[voice]\nenabled = true\n')
    chamado = {}
    def fake_backfill(cfg, **kw):
        chamado["ok"] = True
        return [tmp_path / "n1.md", tmp_path / "n2.md"]
    monkeypatch.setattr("voxlog.voice_backfill.backfill", fake_backfill)
    rc = cli.main(["voice-backfill", "--config", str(cfg_file)])
    assert rc == 0 and chamado["ok"]
    assert "2" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_voice_backfill.py -k cli -q`
Expected: FAIL — `invalid choice: 'voice-backfill'`.

- [ ] **Step 3: Implement** — em `src/voxlog/cli.py`, após o parser do `whatsapp`:

```python
    pvb = sub.add_parser("voice-backfill", help="re-diariza reuniões passadas")
    pvb.add_argument("--config", default=str(_DEFAULT_CFG))
    pvs = sub.add_parser("voice-status", help="status do perfil de voz/diarização")
    pvs.add_argument("--config", default=str(_DEFAULT_CFG))
```

E antes do `return 1` final:

```python
    if args.cmd == "voice-backfill":
        from . import voice_backfill
        notas = voice_backfill.backfill(cfg)
        print(f"{len(notas)} notas re-diarizadas")
        for n in notas:
            print(str(n))
        return 0

    if args.cmd == "voice-status":
        print(f"voice_enabled: {cfg.voice_enabled}")
        print(f"diarize_endpoint: {cfg.voice_diarize_endpoint}")
        return 0
```

> Use `from . import voice_backfill` + `voice_backfill.backfill(cfg)` para o monkeypatch funcionar.

- [ ] **Step 4: Run tests** — `./.venv/bin/python -m pytest -q` → PASS (suite inteira, sem regressões).

- [ ] **Step 5: Commit**

```bash
git add src/voxlog/cli.py tests/test_voice_backfill.py
git commit -m "feat(voz): subcomandos voice-backfill e voice-status

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Artefatos do avell — enrollment, serviço WhisperX, runbook

> Entrega **arquivos versionados** (script de enrollment, serviço, requirements, runbook). Sem teste unitário no repo (precisa de GPU + modelos + token HF); a verificação é executar no avell (Step final). Caminhos do usuário no avell são `jv`.

**Files:**
- Create: `setup/avell/voice_enroll.py`
- Create: `setup/avell/whisperx-service/server.py`
- Create: `setup/avell/whisperx-service/requirements.txt`
- Create: `setup/avell/whisperx-service/voice-diarize.service`
- Create: `docs/voz-deploy.md`

- [ ] **Step 1: requirements** — criar `setup/avell/whisperx-service/requirements.txt`:

```
torch==2.2.2
torchaudio==2.2.2
whisperx==3.1.5
pyannote.audio==3.1.1
speechbrain==1.0.0
flask==3.0.3
numpy<2
```

- [ ] **Step 2: enrollment** — criar `setup/avell/voice_enroll.py`:

```python
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
    req = urllib.request.Request(BRIDGE, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.loads(r.read())
    return res.get("path") if res.get("success") else None

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
    enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                         run_opts={"device": "cuda" if torch.cuda.is_available() else "cpu"})
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
                import torchaudio
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
```

- [ ] **Step 3: serviço** — criar `setup/avell/whisperx-service/server.py`:

```python
#!/usr/bin/env python3
"""Serviço de diarização (:5051). POST /v1/audio/diarize file=@audio
-> {language, speakers, text, segments}. Rotula 'Eu' via match com perfil_eu (ECAPA)."""
import json, os, tempfile
from pathlib import Path
import numpy as np
import torch, torchaudio, whisperx
from flask import Flask, request, jsonify
from speechbrain.inference.speaker import EncoderClassifier

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
HF_TOKEN = os.environ["HF_TOKEN"]
CFG = Path.home() / ".config/voxlog"
PERFIL = np.load(CFG / "perfil_eu.npy") if (CFG / "perfil_eu.npy").exists() else None
THRESHOLD = json.loads((CFG / "perfil_eu.json").read_text()).get("threshold", 0.5) \
    if (CFG / "perfil_eu.json").exists() else 0.5

app = Flask(__name__)
_wx = whisperx.load_model("medium", DEVICE, compute_type="int8", language="pt")
_enc = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb",
                                      run_opts={"device": DEVICE})

def _embed(wav_path, start, end):
    sig, sr = torchaudio.load(wav_path)
    a, b = int(start * sr), int(end * sr)
    seg = sig[:, a:b] if b > a else sig
    e = _enc.encode_batch(seg).squeeze().detach().cpu().numpy()
    return e / (np.linalg.norm(e) + 1e-9)

@app.post("/v1/audio/diarize")
def diarize():
    f = request.files["file"]
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, f.filename or "audio.m4a"); f.save(src)
        wav = os.path.join(td, "audio.wav")
        os.system(f"ffmpeg -y -i '{src}' -ar 16000 -ac 1 '{wav}' >/dev/null 2>&1")
        audio = whisperx.load_audio(wav)
        result = _wx.transcribe(audio, batch_size=8)
        align, meta = whisperx.load_align_model(language_code="pt", device=DEVICE)
        result = whisperx.align(result["segments"], align, meta, audio, DEVICE)
        diar = whisperx.DiarizationPipeline(use_auth_token=HF_TOKEN, device=DEVICE)
        dseg = diar(audio)
        result = whisperx.assign_word_speakers(dseg, result)
        # match cada falante ao perfil_eu
        eu_label = None
        if PERFIL is not None:
            best, best_sim = None, -1.0
            spk_seg = {}
            for s in result["segments"]:
                spk_seg.setdefault(s.get("speaker", "SPEAKER_?"), s)
            for spk, s in spk_seg.items():
                sim = float(np.dot(_embed(wav, s["start"], s["end"]), PERFIL))
                if sim > best_sim:
                    best, best_sim = spk, sim
            if best_sim >= THRESHOLD:
                eu_label = best
        # renomeia rótulos
        ordem, nomes, n = {}, {}, 2
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
```

- [ ] **Step 4: systemd unit** — criar `setup/avell/whisperx-service/voice-diarize.service`:

```ini
[Unit]
Description=voxlog — serviço de diarização (WhisperX :5051)
After=network-online.target

[Service]
Environment=HF_TOKEN=COLOQUE_SEU_TOKEN_HF
WorkingDirectory=/home/jv/products/whisperx-service
ExecStart=/home/jv/products/whisperx-service/.venv/bin/python server.py
Restart=on-failure

[Install]
WantedBy=default.target
```

- [ ] **Step 5: runbook** — criar `docs/voz-deploy.md`:

````markdown
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
````

- [ ] **Step 6: Verificação manual no avell** (não é teste automatizado):

```bash
# enrollment gerou o perfil?
ssh avell_ai_server_tailscale "ls -la ~/.config/voxlog/perfil_eu.npy ~/.config/voxlog/perfil_eu.json"
# serviço responde e rotula?
ssh avell_ai_server_tailscale "curl -sS -F file=@<uma_reuniao>.m4a http://localhost:5051/v1/audio/diarize | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"speakers\"]); print(d[\"text\"][:200])'"
```
Esperado: `speakers` inclui "Eu" e a transcrição vem rotulada.

- [ ] **Step 7: Commit**

```bash
git add setup/avell/ docs/voz-deploy.md
git commit -m "feat(voz): serviço WhisperX (:5051) + enrollment + runbook (avell)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review (preenchido na escrita)

**Cobertura do spec:**
- §2.1 enrollment auto do WhatsApp → Task 7 (`voice_enroll.py`, ~200 amostras, ECAPA, centroide).
- §2.2 diarização completa + rótulo "Eu" → Task 7 (serviço: whisperx + match perfil).
- §2.3 WhisperX+pyannote + token HF → Task 7 (requirements + runbook A).
- §2.4 qualidade primeiro (medium, sequência) → Task 7 (`load_model("medium", int8)`).
- §2.5 só reunião + **backfill** → Task 4 (live) + Task 5/6 (backfill).
- §4 arquitetura server-side (match no avell) → Task 7 serviço.
- §5.2 mudanças no voxlog (config/transcribe/process/vault/cli) → Tasks 1,2,4,5,6. **Nota:** `vault.py` NÃO muda — a transcrição diarizada é só uma string que flui pela renderização atual de transcrição (DRY); o backfill (Task 5) cuida do formato "(diarizada)" nas notas existentes.
- §6 enrollment detalhes (amostragem, wav 16k, centroide, idempotente) → Task 7.
- §7 matching (cosseno, threshold, mesmo modelo) → Task 7 serviço.
- §8 formato na nota ("Eu"/"Falante 2") → Task 4 (live, via texto do serviço) + Task 5 (backfill).
- §9 fallback (serviço/perfil ausente → :5050) → Task 4 (try/except no diarize) e Task 5 (except → pula).
- §10 fora de escopo → respeitado (só "Eu"; não toca WhatsApp/Discord; batch).
- §11 riscos (VRAM, HF, modelo consistente, qualidade enrollment, rota áudio) → runbook + verificação manual (Task 7 Step 6).

**Placeholders:** nenhum "TBD"; o `COLOQUE_SEU_TOKEN_HF` na unit é um valor que o usuário preenche no deploy (documentado no runbook), não um furo de plano.

**Consistência de tipos:** `transcribe_diarized(audio, cfg, curl=)->str` (Task 2) usado em 4/5; `combine_segments(segs, dest, runner=)->Path` (Task 3) usado em 4; `backfill(cfg, _diarize=)->list[Path]` (Task 5) usado em 6; contrato do `:5051` (`text`) consumido por Task 2 e produzido por Task 7. `is_diarized`/`replace_transcript`/`note_audio_path`/`find_meeting_notes` definidos e usados só na Task 5.
