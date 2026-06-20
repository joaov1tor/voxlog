# voxlog — Gatilhos Inteligentes (Subprojeto A) — Design

- **Data:** 2026-06-20
- **Status:** Aprovado (brainstorm) → próximo: plano de implementação
- **Base:** roda sobre a captura atual (BlackHole + `voxlog-Aggregate` + `record.sh`), que já funciona.
- **Fora de escopo (subprojetos futuros):** B) captura nativa Swift (zero-setup, sem BlackHole); C) distribuição p/ amigos (portabilidade + setup.sh). Este doc cobre só A.

## 1. Objetivo

Tornar o disparo da gravação automático e sem esquecimentos no dia a dia de trabalho, com controle estilo Notion (popup "gravar?"), respeitando horário comercial, lembrando reuniões presenciais, e lidando bem com reuniões longas.

### Requisitos confirmados
| Tema | Decisão |
|---|---|
| Janela de atividade | Auto-detecção/popup só **seg–sex, 8h–18h**. Fora disso, sem popup; **⌥⌘R manual sempre funciona**. |
| Gatilho de reunião | **Popup estilo Notion** ao detectar reunião: [Gravar] [Agora não] [Sempre neste app]. |
| Presencial (Ter/Qui) | **Lembrete fixo** periódico nesses dias (notificação) — sem integração de calendário. |
| Reuniões longas | **Gravação em segmentos (~20 min)**; uma nota só ao final, com resumo em camadas. |

## 2. Componentes (tudo no `orchestrator/init.lua` + ajustes em `record.sh` e no pacote Python)

### 2.1 Janela de horário (schedule gate) — Lua
- Config no topo do init.lua: `ACTIVE_DAYS = {2,3,4,5,6}` (zsh/os.date: 1=domingo…7=sábado → seg-sex = 2..6), `ACTIVE_START = 8`, `ACTIVE_END = 18`.
- Função `in_window()` usa `os.date("*t")` (wday, hour). O timer de auto-detecção só age se `in_window()`.
- Fora da janela: nenhum popup/auto; `toggleNote` (⌥⌘R) continua livre.

### 2.2 Popup de detecção (estilo Notion) — Lua
- O timer (3s) detecta reunião = mic em uso **e** app-alvo ativo **e** `in_window()`.
- Em vez de gravar direto, mostra **notificação interativa** (`hs.notify`) com botões:
  - **Gravar** (`actionButtonTitle`) → inicia gravação (segmentada) `tipo=reuniao, origem=<app>`.
  - **Sempre neste app** (`additionalActions`) → grava agora **e** adiciona o app a `~/.config/voxlog/always.json`; nas próximas, esse app grava direto sem perguntar.
  - **Agora não** (ignorar/fechar) → não grava esta sessão.
- **Debounce:** uma notificação por sessão de reunião. Estado `M.prompted_session` é setado quando o popup aparece e limpo quando o mic é liberado (fim da reunião). Não repergunta enquanto o mic seguir em uso.
- Apps em `always.json`: pulam o popup e gravam automaticamente (dentro da janela).

### 2.3 Lembrete presencial (Ter/Qui) — Lua
- Config: `PRESENCIAL_DAYS = {3,5}` (ter, qui), `PRESENCIAL_REMINDER_MIN = 60`.
- Um timer separado (a cada `PRESENCIAL_REMINDER_MIN` min): se dia ∈ PRESENCIAL_DAYS e `in_window()` e **não há gravação em curso**, mostra notificação: "📍 Dia de TOTVS — grave reuniões presenciais com ⌥⌘R".
- Não dispara gravação; só lembra. Some quando uma gravação está ativa (não enche o saco durante a call).

### 2.4 Reuniões longas — gravação em segmentos
- **`record.sh`**: modo segmentado. ffmpeg com `-f segment -segment_time 1200 -reset_timestamps 1 -segment_format mp4 -movflags +frag_keyframe+empty_moov+default_base_moof "<staging>/<sessao>_%03d.m4a"`. Cada ~20 min fecha um arquivo `<sessao>_000.m4a`, `_001.m4a`, …
  - `<sessao>` = `YYYYMMDD-HHMMSS_<tipo>` (timestamp de início da sessão, vira o id da nota).
  - Mantém o `|| true` no lookup do device e o PATH export (correções já feitas).
- **Processamento por sessão** (Python): novo conceito de "sessão" agrupando os segmentos.
  - Whisper-GPU transcreve cada segmento (sequencial — o endpoint tem lock). Os segmentos podem ser transcritos **assim que fecham** (watcher na pasta) acumulando o texto da sessão; ao parar, finaliza.
  - **Resumo em camadas (Codex):** se houver >1 segmento, resume cada segmento, depois um passe final no Codex juntando os resumos parciais → resumo único + itens de ação consolidados. (Evita estourar contexto em 2h.)
  - **Uma nota** por sessão: frontmatter (data, hora_inicio = início da sessão, duracao_min = soma), transcrição completa concatenada, resumo final. Áudio: concatena os segmentos num único `.m4a` arquivado (ffmpeg concat) ou linka os segmentos.
- **Resiliência:** travou no meio → segmentos já fechados estão salvos e transcritos; perde no máximo o último (~20 min) e ainda gera nota com o que tem.

## 3. Fluxo de dados (resumo)
```
timer 3s (Lua) ── in_window? ── mic+app-alvo? ──┬─ app em always.json → grava (segmentado)
                                                 └─ senão → popup Notion → [Gravar] → grava (segmentado)
gravação (record.sh, segmentos 20min) → staging/<sessao>_NNN.m4a
   → (watcher) transcreve cada segmento (Whisper-GPU) acumulando na sessão
parar (⌥⌘R / app fechou / mic liberado) → resumo em camadas (Codex) → 1 nota no Obsidian
timer lembrete (Lua) ── dia∈{ter,qui} & janela & sem gravação → notificação "grave presencial"
```

## 4. Configuração (novos campos)
- `init.lua` (constantes no topo): `ACTIVE_DAYS`, `ACTIVE_START`, `ACTIVE_END`, `PRESENCIAL_DAYS`, `PRESENCIAL_REMINDER_MIN`, `SEGMENT_SECONDS=1200`.
- `~/.config/voxlog/always.json`: lista de apps que gravam sem perguntar (mantida pelo botão "Sempre neste app").
- Python: o processador ganha modo "sessão" (agrupa `<sessao>_NNN.m4a`).

## 5. Tratamento de erros
- Popup ignorado/sem resposta → não grava (default seguro).
- Segmento que falha transcrição → marca a sessão como parcial, mantém o áudio, nota sai com os segmentos que deram certo + aviso.
- Codex falha no resumo final → nota com transcrição completa + `resumido_por: nenhum` (sem ollama, como já definido).
- Fora da janela → nada automático; manual sempre disponível.
- Sessão sem segmentos válidos (clipe curto) → descartada (regra de min_duration por sessão).

## 6. Testes
- **Lua (verificação manual):** `in_window()` (mock de dia/hora), popup aparece só na janela, "Sempre neste app" persiste e pula popup, lembrete só Ter/Qui e não durante gravação, debounce (um popup por sessão).
- **Python (pytest):** agrupamento de segmentos numa sessão; resumo em camadas (mock do codex por segmento + final); nota única com duração somada; sessão parcial quando um segmento falha; concat de áudio.
- **E2E:** reunião curta (1 segmento, 1 nota); reunião >20min (2+ segmentos → 1 nota com resumo em camadas); fora da janela (sem popup).

## 7. Fases sugeridas
1. Janela de horário + lembrete presencial (Lua puro, rápido).
2. Popup Notion + `always.json` + debounce.
3. Segmentos no record.sh + modo sessão no processador + resumo em camadas.

## 8. Questões em aberto (resolver no plano)
- Mecanismo exato do popup: `hs.notify` com `additionalActions` vs um mini `hs.webview` (decidir no plano; default `hs.notify`).
- Transcrição por segmento **ao vivo** (watcher) vs só no fim — começar pelo fim (mais simples) e evoluir p/ ao vivo se necessário.
- Concatenar áudio dos segmentos vs manter segmentos linkados na nota.
