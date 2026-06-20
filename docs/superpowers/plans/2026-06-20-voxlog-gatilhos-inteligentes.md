# voxlog — Gatilhos Inteligentes (Subprojeto A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Disparo inteligente da gravação no voxlog — janela de horário (seg-sex 8-18), popup estilo Notion ao detectar reunião, lembrete presencial Ter/Qui, e gravação de reuniões longas em segmentos com uma nota e resumo em camadas.

**Architecture:** O orquestrador Hammerspoon (`orchestrator/init.lua`) ganha porteiro de horário, popup interativo (`hs.notify`) com memória de apps (`always.json`) e timer de lembrete. O `record.sh` ganha modo segmentado (ffmpeg segment muxer). O pacote Python ganha "modo sessão": agrupa os segmentos de uma gravação, transcreve cada um (Whisper-GPU já existente), faz resumo em camadas via Codex e escreve UMA nota. Roda sobre a captura atual (BlackHole), que já funciona.

**Tech Stack:** Hammerspoon (Lua), ffmpeg (segment muxer), Python 3.12 (pytest), Whisper-GPU remoto + Codex (já integrados).

## Global Constraints

- Roda sobre a captura atual: `voxlog-Aggregate` (BlackHole) + `record.sh`. Não mexer na camada de captura (isso é o subprojeto B, futuro).
- Janela ativa: **seg–sex, 8h–18h**. `os.date` `wday`: 1=domingo … 7=sábado → seg-sex = `{2,3,4,5,6}`. Ter/Qui = `{3,5}`.
- Segmento padrão: **1200s (20 min)**, configurável.
- Resumo: **Codex** (sem fallback ollama); falha → `resumido_por: nenhum`. Transcrição: Whisper-GPU remoto (`whisper_endpoint`) com fallback local.
- ⌥⌘R manual SEMPRE funciona, inclusive fora da janela.
- Python: venv `.venv`, `pytest` via `./.venv/bin/pytest`. Conventional commits (`git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com"`).
- Lua/shell não têm runtime de teste local → verificação manual (descrita em cada task). Não improvisar Lua não testável: transcrever o código deste plano verbatim.

## File Structure
- `orchestrator/init.lua` (modificar): porteiro de horário, popup, debounce, always.json, lembrete, chamada segmentada + process-session.
- `recorder/record.sh` (modificar): modo segmentado.
- `src/voxlog/summarize.py` (modificar): `summarize_segments` (resumo em camadas).
- `src/voxlog/session.py` (criar): `process_session` (agrupa segmentos → 1 nota).
- `src/voxlog/cli.py` (modificar): subcomando `process-session`.
- `tests/test_summarize.py`, `tests/test_session.py`.

---

### Task 1: Janela de horário + lembrete presencial (init.lua)

**Files:**
- Modify: `orchestrator/init.lua`

**Interfaces:**
- Consumes: funções existentes `startRecording`, `stopRecording`, `M.task`, o timer `M.timer`.
- Produces: `in_window()` (bool), constantes `ACTIVE_DAYS/ACTIVE_START/ACTIVE_END/PRESENCIAL_DAYS/PRESENCIAL_REMINDER_MIN`; timer de lembrete `M.reminder_timer`.

- [ ] **Step 1: Adicionar constantes e `in_window()` no topo do init.lua**

Logo após a linha `M.paused = false` (perto das definições de auto-detecção), adicione:

```lua
-- ===== Janela de horário (seg-sex 8-18) =====
local ACTIVE_DAYS = { [2]=true, [3]=true, [4]=true, [5]=true, [6]=true } -- wday: 1=dom..7=sab
local ACTIVE_START, ACTIVE_END = 8, 18
local PRESENCIAL_DAYS = { [3]=true, [5]=true }   -- ter, qui
local PRESENCIAL_REMINDER_MIN = 60

local function in_window()
  local t = os.date("*t")
  return ACTIVE_DAYS[t.wday] and t.hour >= ACTIVE_START and t.hour < ACTIVE_END
end
```

- [ ] **Step 2: Gatear a auto-detecção pela janela**

No corpo do `M.timer` (timer de 3s da auto-detecção), troque a primeira linha `if M.paused then return end` por:

```lua
  if M.paused or not in_window() then return end
```

- [ ] **Step 3: Adicionar o timer de lembrete presencial**

Logo após o bloco `M.timer:start()`, adicione:

```lua
-- ===== Lembrete presencial (Ter/Qui) =====
M.reminder_timer = hs.timer.new(PRESENCIAL_REMINDER_MIN * 60, function()
  local t = os.date("*t")
  if PRESENCIAL_DAYS[t.wday] and in_window() and not M.task then
    hs.notify.new({title = "voxlog",
      informativeText = "📍 Dia de TOTVS — grave reuniões presenciais com ⌥⌘R"}):send()
  end
end)
M.reminder_timer:start()
```

- [ ] **Step 4: Verificação de sintaxe visual + commit**

Releia o `init.lua` confirmando: `in_window()` definida antes do uso; um único `M.timer` e um `M.reminder_timer`; `end`s balanceados. (Sem runtime Lua local — verificação é visual + teste manual no Hammerspoon depois.)

```bash
git add orchestrator/init.lua
git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com" commit -m "feat: schedule window gate and in-person reminder in orchestrator"
```

- [ ] **Step 5: Verificação MANUAL (deferida ao usuário)**

Reload do Hammerspoon. Dentro de 8-18 em dia útil: auto-detecção funciona. Fora (ou fim de semana): nenhum popup, mas ⌥⌘R ainda grava. Ter/Qui: aparece a notificação de lembrete a cada 60min (quando não está gravando).

---

### Task 2: Popup estilo Notion + memória de apps (init.lua)

**Files:**
- Modify: `orchestrator/init.lua`

**Interfaces:**
- Consumes: `startRecording(tipo, origem)`, `in_window()`, `activeTargetApp()` (já existe), `M.task`.
- Produces: `always.json` em `~/.config/voxlog/always.json`; funções `loadAlways()`, `addAlwaysApp(app)`, `promptMeeting(app)`; estado `M.prompted` (debounce).

- [ ] **Step 1: Adicionar memória de apps (always.json) e o popup**

Antes do `M.timer = hs.timer.new(...)`, adicione:

```lua
-- ===== Memória de apps que gravam sem perguntar =====
local ALWAYS_PATH = os.getenv("HOME") .. "/.config/voxlog/always.json"
local function loadAlways()
  return hs.json.read(ALWAYS_PATH) or {}
end
local function isAlways(app)
  for _, a in ipairs(loadAlways()) do if a == app then return true end end
  return false
end
local function addAlwaysApp(app)
  local list = loadAlways()
  for _, a in ipairs(list) do if a == app then return end end
  table.insert(list, app)
  hs.fs.mkdir(os.getenv("HOME") .. "/.config/voxlog")
  hs.json.write(list, ALWAYS_PATH, true, true)
end

-- ===== Popup estilo Notion =====
local function promptMeeting(app)
  hs.notify.new(function(notif)
    local at = notif:activationType()
    if at == hs.notify.activationTypes.actionButtonClicked then
      startRecording("reuniao", app); M.auto = true; M.auto_app = app
    elseif at == hs.notify.activationTypes.additionalActionClicked then
      addAlwaysApp(app)
      startRecording("reuniao", app); M.auto = true; M.auto_app = app
    end
  end, {
    title = "voxlog",
    informativeText = "Reunião detectada (" .. app .. ") — gravar?",
    hasActionButton = true,
    actionButtonTitle = "Gravar",
    additionalActions = { "Sempre neste app" },
    withdrawAfter = 0,
  }):send()
end
```

- [ ] **Step 2: Trocar o auto-início silencioso pelo popup (com debounce)**

No `M.timer`, substitua o ramo de auto-início. De:

```lua
  if (not M.task) and micInUse() and target then
    startRecording("reuniao", target)
    M.auto = true
    M.auto_app = target
  elseif M.task and M.auto and M.auto_app and (not appRunning(M.auto_app)) then
```

Para:

```lua
  if (not M.task) and micInUse() and target then
    if isAlways(target) then
      startRecording("reuniao", target); M.auto = true; M.auto_app = target
    elseif not M.prompted then
      promptMeeting(target); M.prompted = true   -- pergunta 1x por sessão
    end
  elseif M.task and M.auto and M.auto_app and (not appRunning(M.auto_app)) then
```

- [ ] **Step 3: Resetar o debounce quando a reunião acaba**

Ainda no `M.timer`, no ramo de parada (`stopRecording()`), e também quando o mic é liberado sem ter gravado, limpe `M.prompted`. Após a linha `M.auto_app = nil` (dentro do `elseif` de parada), adicione `M.prompted = false`. E adicione um ramo final antes do `end` do if encadeado:

```lua
  elseif (not M.task) and (not micInUse()) then
    M.prompted = false   -- mic livre: pode perguntar de novo na próxima reunião
  end
```

Inicialize `M.prompted = false` junto das outras flags de `M` (na tabela inicial, adicione `prompted = false`).

- [ ] **Step 4: Commit**

```bash
git add orchestrator/init.lua
git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com" commit -m "feat: Notion-style record popup with per-app memory and debounce"
```

- [ ] **Step 5: Verificação MANUAL (deferida ao usuário)**

Reload. Entrar numa call (Zoom) na janela → aparece notificação "gravar?" com [Gravar] e [Sempre neste app]. "Gravar" inicia; "Sempre neste app" grava e nas próximas não pergunta mais pra esse app. Só 1 popup por reunião.

---

### Task 3: Modo segmentado no record.sh

**Files:**
- Modify: `recorder/record.sh`

**Interfaces:**
- Consumes: nada novo.
- Produces: `record.sh <tipo> <staging_dir> [segment_seconds]` — grava em segmentos `<TS>_<tipo>_%03d.m4a`; imprime na 1ª linha da stdout o **session id** `<TS>_<tipo>` (não mais um único arquivo). `segment_seconds` default 1200.

- [ ] **Step 1: Reescrever a parte de saída do record.sh para segmentos**

No `recorder/record.sh`, troque o bloco que define `OUT`, faz `echo "$OUT"` e o `exec ffmpeg` final por:

```bash
SEG="${3:-1200}"                       # segundos por segmento (default 20min)
SESSION="${TS}_${TIPO}"                 # id da sessão (prefixo dos segmentos)
echo "$SESSION"                          # 1a linha stdout = session id

# Grava em segmentos; cada um é MP4 fragmentado (válido mesmo se cortado).
exec ffmpeg -hide_banner -loglevel warning \
  -f avfoundation -i ":${IDX}" \
  -c:a aac -b:a 192k \
  -f segment -segment_time "$SEG" -reset_timestamps 1 \
  -segment_format mp4 -movflags +frag_keyframe+empty_moov+default_base_moof \
  "$STAGING/${SESSION}_%03d.m4a"
```

(Mantém o cabeçalho, `set -euo pipefail`, o `export PATH`, o `mkdir -p "$STAGING"`, o `TS=...` e o lookup de `IDX` com `|| true` — só muda a saída.)

- [ ] **Step 2: Verificação mecânica — segmentos de 3s**

Run (grava ~7s com segmentos de 3s → deve gerar 2-3 arquivos):
```bash
cd /Volumes/SSD/Dropbox/Developments/gravador_audio
rm -f "$HOME/Gravacoes/staging/"*.m4a
./recorder/record.sh nota "$HOME/Gravacoes/staging" 3 >/tmp/seg.txt 2>/tmp/sege.txt &
SH=$!; ( sleep 7; kill -TERM "$SH" 2>/dev/null ) & SLP=$!
wait "$SH" 2>/dev/null; wait "$SLP" 2>/dev/null
echo "session id: $(cat /tmp/seg.txt)"
ls -la "$HOME/Gravacoes/staging/"*.m4a
```
Expected: stdout imprime um session id tipo `20260620-XXXXXX_nota`; existem múltiplos arquivos `..._000.m4a`, `..._001.m4a`, … cada um com duração válida (ffprobe). (Áudio mudo é esperado se rodado pelo Termius — só validamos a segmentação.)

- [ ] **Step 3: Limpar e commit**

```bash
rm -f "$HOME/Gravacoes/staging/"*.m4a
git add recorder/record.sh
git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com" commit -m "feat: segmented recording in record.sh (ffmpeg segment muxer)"
```

---

### Task 4: Resumo em camadas (summarize_segments)

**Files:**
- Modify: `src/voxlog/summarize.py`
- Test: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `Config`, `Summary`, `summarize(transcript, cfg, force_local, runner)`, `_codex_cmd`, `build_prompt` (já existem).
- Produces: `summarize_segments(transcripts: list[str], cfg: Config, force_local: bool = False, runner=None) -> Summary`. 1 segmento → igual a `summarize`. >1 → resume cada um e faz um passe final combinando.

- [ ] **Step 1: Escrever os testes (falham)**

Append em `tests/test_summarize.py`:

```python
def test_summarize_segments_um_so_delega():
    cfg = Config(summarizer="codex")
    def runner(cmd, input_text):
        return json.dumps(PAYLOAD)
    s = summarize_segments(["transcricao unica"], cfg, runner=runner)
    assert s.assunto == "Planejamento Sprint 12"
    assert s.resumido_por == "codex"


def test_summarize_segments_combina_varios():
    cfg = Config(summarizer="codex")
    calls = []
    final = {"resumo": "resumo final", "assunto": "Reuniao Longa",
             "tags": ["x"], "participantes": ["Ana"], "acoes": ["fazer y"]}
    def runner(cmd, input_text):
        calls.append(input_text)
        # 2 parciais + 1 final = 3 chamadas; a final recebe os parciais juntos
        return json.dumps(final)
    s = summarize_segments(["seg1", "seg2"], cfg, runner=runner)
    assert len(calls) == 3                      # 2 segmentos + combine
    assert s.assunto == "Reuniao Longa"
    assert s.resumido_por == "codex"
```

Garanta o import no topo: `from voxlog.summarize import Summary, parse_summary_json, summarize, build_prompt, summarize_segments` (adicione `summarize_segments`).

- [ ] **Step 2: Rodar (falha)**

Run: `./.venv/bin/pytest tests/test_summarize.py -q`
Expected: FAIL (`ImportError: cannot import name 'summarize_segments'`).

- [ ] **Step 3: Implementar `summarize_segments`**

Em `src/voxlog/summarize.py`, adicione ao fim:

```python
_COMBINE_PROMPT = """Você recebe vários RESUMOS PARCIAIS de segmentos de uma mesma
reunião, em ordem. Combine tudo em UM resumo coeso. Responda APENAS com um objeto
JSON válido com as chaves: "resumo" (string), "assunto" (string curta), "tags"
(array), "participantes" (array), "acoes" (array consolidada).

RESUMOS PARCIAIS:
\"\"\"
{parciais}
\"\"\"
"""


def summarize_segments(transcripts, cfg, force_local: bool = False, runner=None) -> Summary:
    transcripts = [t for t in transcripts if t and t.strip()]
    if not transcripts:
        return Summary(resumido_por="nenhum")
    if len(transcripts) == 1:
        return summarize(transcripts[0], cfg, force_local=force_local, runner=runner)
    # resume cada segmento, depois combina
    parciais = []
    for t in transcripts:
        s = summarize(t, cfg, force_local=force_local, runner=runner)
        parciais.append(s.resumo or t[:500])
    run = runner or _default_runner
    backends = ([("ollama", _ollama_cmd(cfg))] if (force_local or cfg.summarizer == "ollama")
                else [("codex", _codex_cmd(cfg))])
    prompt = _COMBINE_PROMPT.format(parciais="\n\n".join(parciais))
    for name, cmd in backends:
        try:
            return parse_summary_json(run(cmd, prompt), name)
        except Exception:
            continue
    return Summary(resumido_por="nenhum")
```

- [ ] **Step 4: Rodar (passa) + suite**

Run: `./.venv/bin/pytest tests/test_summarize.py -q`
Expected: PASS (todos). Depois `./.venv/bin/pytest -q` (suite inteira verde).

- [ ] **Step 5: Commit**

```bash
git add src/voxlog/summarize.py tests/test_summarize.py
git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com" commit -m "feat: layered summary for multi-segment sessions"
```

---

### Task 5: Processamento de sessão (process_session + CLI)

**Files:**
- Create: `src/voxlog/session.py`
- Modify: `src/voxlog/cli.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `Config`, `transcribe` (T-existente), `summarize_segments` (T4), `NoteMeta`/`write_note` (existente), `file_sha1`/`audio_duration_sec` (de `process.py`).
- Produces: `process_session(staging_dir, session_id, tipo, origem, cfg, force_local=False, *, _transcribe=None, _summarize=None, _duration=None) -> Path | None`. CLI: `voxlog process-session <session_id> [--staging <dir>] --tipo --origem [--local] [--config]`. Preserva todos os segmentos em `_audios/` (sem perder áudio das partes).

- [ ] **Step 1: Escrever os testes (falham)**

Create `tests/test_session.py`:

```python
from pathlib import Path
from voxlog.config import Config
from voxlog.summarize import Summary
from voxlog.session import process_session


def _seg(dirp, name):
    p = dirp / name; p.write_bytes(b"AUDIO"); return p


def test_process_session_uma_nota_de_varios_segmentos(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    _seg(staging, "20260620-101500_reuniao_000.m4a")
    _seg(staging, "20260620-101500_reuniao_001.m4a")
    cfg = Config(vault_path=tmp_path / "v", gravacoes_dir="G", audios_dir="G/_audios")
    summ = Summary(resumo="r", assunto="Reuniao Longa", tags=["t"], resumido_por="codex")
    out = process_session(
        staging, "20260620-101500_reuniao", "reuniao", "Zoom", cfg,
        _transcribe=lambda seg, c: f"texto {seg.name}",
        _summarize=lambda trs, c, fl: summ,
        _duration=lambda p, runner=None: 600.0,
    )
    assert out is not None and out.exists()
    body = out.read_text(encoding="utf-8")
    assert "Reuniao Longa" in out.name
    assert "texto 20260620-101500_reuniao_000.m4a" in body  # transcrição concatenada
    assert 'hora_inicio: "10:15"' in body                   # início vem do session id
    assert "duracao_min: 20" in body                        # 2x600s = 1200s = 20min


def test_process_session_descarta_curto(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    _seg(staging, "20260620-101500_nota_000.m4a")
    cfg = Config(vault_path=tmp_path / "v", min_duration_sec=5.0)
    out = process_session(
        staging, "20260620-101500_nota", "nota", "manual", cfg,
        _transcribe=lambda *a, **k: "t",
        _summarize=lambda *a, **k: Summary(),
        _duration=lambda p, runner=None: 2.0,
    )
    assert out is None
    assert not list(staging.glob("*.m4a"))   # segmentos descartados
```

- [ ] **Step 2: Rodar (falha)**

Run: `./.venv/bin/pytest tests/test_session.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'voxlog.session'`).

- [ ] **Step 3: Implementar `src/voxlog/session.py`**

```python
from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path
from .config import Config
from .transcribe import transcribe as _do_transcribe
from .summarize import summarize_segments as _do_summarize_segments
from .process import file_sha1, audio_duration_sec
from .vault import NoteMeta, write_note


def _session_start(session_id: str) -> datetime:
    # session_id = "YYYYMMDD-HHMMSS_tipo"
    stamp = session_id.split("_")[0]
    return datetime.strptime(stamp, "%Y%m%d-%H%M%S")


def process_session(staging_dir, session_id, tipo, origem, cfg: Config,
                    force_local: bool = False, *, _transcribe=None,
                    _summarize=None, _duration=None) -> Path | None:
    staging = Path(staging_dir)
    segs = sorted(staging.glob(f"{session_id}_*.m4a"))
    if not segs:
        return None
    dur = _duration or audio_duration_sec
    total = sum(dur(s) for s in segs)
    if total < cfg.min_duration_sec:
        for s in segs:
            s.unlink(missing_ok=True)
        return None

    tr = _transcribe or _do_transcribe
    transcripts = [tr(s, cfg) for s in segs]
    full = "\n".join(transcripts)
    summary = (_summarize or _do_summarize_segments)(transcripts, cfg, force_local)

    start = _session_start(session_id)
    audio_filename = f"{start.strftime('%Y-%m-%d %H%M')} {tipo}.m4a"
    meta = NoteMeta(
        tipo=tipo,
        data=start.strftime("%Y-%m-%d"),
        hora_inicio=start.strftime("%H:%M"),
        duracao_min=max(1, round(total / 60)),
        origem=origem,
        audio_filename=audio_filename,
        audio_hash=file_sha1(segs[0]),
    )
    note = write_note(cfg, meta, summary, full, segs[0])  # move segs[0] -> _audios
    # preserva as demais partes em _audios (não perde áudio do restante da reunião)
    audios = cfg.vault_path / cfg.audios_dir
    audios.mkdir(parents=True, exist_ok=True)
    for s in segs[1:]:
        if s.exists():
            shutil.move(str(s), str(audios / s.name))
    return note
```

- [ ] **Step 4: Adicionar o subcomando `process-session` na CLI**

Em `src/voxlog/cli.py`, dentro de `main()`, após o parser do subcomando `process`, adicione um novo subparser e o roteamento:

```python
    ps = sub.add_parser("process-session", help="processa os segmentos de uma sessão")
    ps.add_argument("session_id")
    ps.add_argument("--staging", default=str(Path("~/Gravacoes/staging").expanduser()))
    ps.add_argument("--tipo", default="reuniao", choices=["nota", "reuniao"])
    ps.add_argument("--origem", default="manual")
    ps.add_argument("--local", action="store_true")
    ps.add_argument("--config", default=str(_DEFAULT_CFG))
```

E no roteamento (depois do bloco que trata `args.cmd == "process"`), adicione:

```python
    if args.cmd == "process-session":
        from .session import process_session
        cfg = load_config(Path(args.config))
        try:
            out = process_session(args.staging, args.session_id, args.tipo,
                                  args.origem, cfg, force_local=args.local)
        except Exception as e:
            print(f"voxlog: erro na sessão '{args.session_id}': {e}", file=sys.stderr)
            return 1
        if out is None:
            print("descartado (sessão curta/sem segmentos)")
            return 0
        print(str(out))
        return 0
```

(Se o `main()` atual usa `process_audio` direto sem checar `args.cmd`, ajuste para rotear por `args.cmd` — `process` chama `process_audio`, `process-session` chama `process_session`.)

- [ ] **Step 5: Rodar (passa) + suite + smoke da CLI**

Run: `./.venv/bin/pytest tests/test_session.py -q` → PASS.
Run: `./.venv/bin/pytest -q` → tudo verde.
Run: `./.venv/bin/voxlog process-session --help` → mostra os args.

- [ ] **Step 6: Commit**

```bash
git add src/voxlog/session.py src/voxlog/cli.py tests/test_session.py
git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com" commit -m "feat: session processing (segments -> one note) and process-session CLI"
```

---

### Task 6: Ligar o orquestrador aos segmentos + process-session (init.lua)

**Files:**
- Modify: `orchestrator/init.lua`

**Interfaces:**
- Consumes: `record.sh` em modo segmentado (T3), CLI `process-session` (T5), `startRecording`/`stopRecording`/`process` existentes.
- Produces: gravação dispara `record.sh` (segmentos), captura o **session id** da stdout, e ao parar chama `voxlog process-session <session_id>`.

- [ ] **Step 1: Capturar o session id em vez do caminho de arquivo**

Em `startRecording`, o callback de streaming hoje guarda `M.current_file`. Renomeie semanticamente para session id (o conteúdo agora é o id da sessão, não um arquivo). Troque:

```lua
      if stdout and not M.current_file then
        M.current_file = stdout:match("^%s*([^\n]+)")
      end
```
(continua igual — `M.current_file` agora guarda o session id impresso pelo record.sh).

- [ ] **Step 2: Trocar `process()` para chamar `process-session`**

Substitua a função `process(file, tipo, origem)` por:

```lua
local function process(session, tipo, origem)
  if not session then return end
  local cmd = string.format(
    "export PATH=\"$HOME/anaconda3/bin:/opt/homebrew/bin:/usr/local/bin:$(ls -d $HOME/.nvm/versions/node/*/bin 2>/dev/null | tail -1):$PATH\"; %s process-session '%s' --tipo '%s' --origem '%s' --staging '%s' >> '%s' 2>&1",
    VOXLOG, session, tipo, origem, STAGING, LOG)
  hs.task.new("/bin/zsh", function(code, _, _)
    hs.notify.new({title="voxlog",
      informativeText=(code==0 and "Nota criada ✅" or "Falha — ver ~/Gravacoes/voxlog.log ❌")}):send()
  end, {"-lc", cmd}):start()
end
```

- [ ] **Step 3: Verificação de sintaxe visual + commit**

Releia: `process` recebe `session` e chama `process-session`; `stopRecording` passa `M.current_file` (session id) para `process`. `end`s balanceados.

```bash
git add orchestrator/init.lua
git -c user.name="joaov1tor" -c user.email="joaov1tu@gmail.com" commit -m "feat: orchestrator drives segmented recording + process-session"
```

- [ ] **Step 4: Verificação MANUAL E2E (deferida ao usuário)**

Reload do Hammerspoon. (a) Reunião curta (1 segmento) → 1 nota. (b) Reunião >20min (2+ segmentos) → 1 nota só, com transcrição concatenada e resumo em camadas. (c) Conferir `~/Gravacoes/voxlog.log` em caso de falha.

---

## Self-Review

**Spec coverage:**
- Janela 8-18 seg-sex → Task 1 ✓
- Lembrete Ter/Qui → Task 1 ✓
- Popup Notion + "Sempre neste app" + debounce → Task 2 ✓
- Segmentos no record.sh → Task 3 ✓
- Resumo em camadas → Task 4 ✓
- Sessão → 1 nota → Task 5 ✓
- Orquestrador liga tudo → Task 6 ✓
- Fora-da-janela mantém ⌥⌘R manual → Task 1 (gate só na auto-detecção) ✓
- Erros (popup ignorado, segmento falho, codex falha, sessão curta) → Tasks 2/4/5 ✓

**Itens deixados como refino consciente (documentados nas "Questões em aberto" do spec):** transcrição por segmento AO VIVO (este plano processa no fim, ao parar); a nota linka a 1ª parte de áudio no frontmatter mas TODAS as partes ficam preservadas em `_audios/` (concatenar num arquivo único fica como refino futuro). Mecanismo do popup = `hs.notify` (escolhido).

**Placeholder scan:** sem TBD/TODO; todo passo com código real.

**Type consistency:** `summarize_segments(transcripts, cfg, force_local, runner)` (T4) é consumida por `process_session` via `_summarize` (T5) com assinatura `(transcripts, cfg, force_local)`; `transcribe(seg, cfg)` (existente) usada como `_transcribe`; `NoteMeta`/`write_note`/`file_sha1`/`audio_duration_sec` reusados com as assinaturas atuais. CLI roteia `process` (process_audio) e `process-session` (process_session).
