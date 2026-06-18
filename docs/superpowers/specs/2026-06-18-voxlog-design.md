# voxlog — Design

- **Data:** 2026-06-18
- **Status:** Aprovado (brainstorm) → próximo: plano de implementação
- **Repo:** https://github.com/joaov1tor/voxlog (privado)

## 1. Objetivo

Capturar **tudo que o usuário fala durante o dia** — notas de voz avulsas e reuniões
(Meet, Discord, Teams, Zoom ou qualquer app) — e transformar cada captura em uma nota
**organizada por momento e por assunto** no Obsidian, com transcrição local e resumo por IA.

### Requisitos confirmados

| Requisito | Decisão |
|---|---|
| Modelo de captura | **Híbrido**: atalho manual (notas) + auto-detecção de reunião |
| Detecção automática | Por **microfone em uso** + app-alvo ativo (Zoom/Teams/Meet/Discord) |
| Áudio capturado | **Mic + áudio do sistema** juntos |
| Destino | **Obsidian** (markdown local), vault `SecundBrain` |
| Organização | Por **momento** (timestamp) e por **assunto** (tags + Central Dataview) |
| Transcrição | **Local** (Whisper), nunca sai do Mac |
| Resumo | **Codex** (padrão) com **fallback Ollama**; opção "só local" por gravação |
| Privacidade | Local-first; com Codex, só o *texto* da transcrição vai à OpenAI |
| Custo | Grátis/open-source + assinatura Codex já existente ($20) |

### Ambiente alvo

- MacBook Pro **M4**, 10 cores, 16 GB, **macOS 15.1**
- Vault Obsidian: `/Volumes/SSD/Dropbox/obsidian/SecundBrain`
- Já instalado: `openai-whisper`, `ollama` (com `llama3.1:8b`), `ffmpeg 7.1.1`,
  `codex` CLI 0.46.0 (autenticado), Python 3.12 (anaconda), Node 24, Discord/Teams/Zoom.

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│  HAMMERSPOON (orquestrador — daemon leve, sempre ativo)      │
│  • AUTO: vigia "mic em uso" + app-alvo → reunião             │
│  • MANUAL: atalho global (⌥⌘R) liga/desliga nota             │
│  • Barra de menu: estado ● / ○ e ações                       │
└───────────────┬───────────────────────────────────────────┘
                │ start / stop
                ▼
┌─────────────────────────────────────────────────────────────┐
│  ffmpeg → grava Aggregate Device (MIC + SISTEMA via          │
│  BlackHole) → ~/Gravacoes/staging/<timestamp>_<tipo>.m4a     │
└───────────────┬───────────────────────────────────────────┘
                │ ao parar, enfileira
                ▼
┌─────────────────────────────────────────────────────────────┐
│  PROCESSADOR (Python, fila serial)                           │
│  1. Whisper transcreve (local, PT+EN)                        │
│  2. Resumir: Codex (codex exec) → fallback Ollama            │
│     → JSON {resumo, assunto, tags, participantes, acoes}     │
│  3. Renderiza markdown e grava nota no vault                 │
│  4. Move áudio p/ _audios, limpa staging                     │
└─────────────────────────────────────────────────────────────┘
```

### Componentes (unidades isoladas)

| Componente | Responsabilidade única | Interface | Depende de |
|---|---|---|---|
| `audio-setup` (doc + script) | BlackHole + Aggregate/Multi-Output | one-time, manual guiado | BlackHole, Audio MIDI |
| `orchestrator` (Hammerspoon/Lua) | Detectar gatilhos, controlar gravação, menu | chama `recorder` e enfileira p/ `processor` | hs.audiodevice, hs.application |
| `recorder` (shell + ffmpeg) | Gravar Aggregate Device em arquivo | `record(tipo) → caminho.m4a` | ffmpeg, Aggregate Device |
| `processor` (Python) | Transcrever + resumir + escrever nota | `process(audio, meta) → nota.md` | whisper, summarizer, vault-writer |
| `summarizer` (Python, plugável) | Gerar resumo estruturado | `summarize(texto, modo) → dict` | codex CLI / ollama |
| `vault-writer` (Python) | Renderizar markdown + frontmatter no vault | `write(meta, resumo, transcrição)` | template, caminho do vault |

## 3. Fluxo de dados

1. **Gatilho**
   - *Auto*: `mic.inUse == true` **e** app-alvo rodando/frontmost → `tipo=reuniao`, `origem=<app>`.
   - *Manual*: atalho `⌥⌘R` → `tipo=nota`, `origem=manual`.
2. **Gravar**: ffmpeg grava Aggregate Device até o stop (mic liberado, ou atalho de novo).
   Lock garante 1 gravação por vez. Clipes < ~5s são descartados.
3. **Enfileirar**: arquivo cai em `staging/`; processador consome serialmente.
4. **Transcrever**: Whisper (modelo multilíngue) → texto + (opcional) timestamps.
5. **Resumir**: `summarizer` no modo escolhido:
   - `codex` (padrão): `codex exec` com prompt pedindo **JSON** {resumo, assunto, tags, participantes, acoes}.
   - `ollama` (fallback/forçado): `llama3.1:8b` com mesmo contrato JSON.
6. **Escrever nota** no vault e **mover áudio** p/ `_audios/`; remove do staging.

### Organização no Obsidian

```
🎙️ Gravações/
  2026/06-Junho/2026-06-18 1430 — Reunião — Planejamento Sprint 12.md
  _audios/2026-06-18 1430 reuniao.m4a
  _Central.md   ← Dataview: por dia, por assunto/tag, reuniões vs notas
```

**Frontmatter da nota:**
```yaml
---
tipo: reuniao            # ou: nota
data: 2026-06-18
hora_inicio: "14:30"
duracao_min: 40
origem: Zoom             # Teams | Meet | Discord | manual
assunto: "Planejamento Sprint 12"
tags: [reuniao, projeto-x, planejamento]
participantes: [João, Maria]
resumido_por: codex      # ollama | nenhum
audio: "[[2026-06-18 1430 reuniao.m4a]]"
---
```

**Corpo:** `## 📌 Resumo` · `## ✅ Itens de ação` · `## 🗣️ Tópicos e decisões` · `## 📝 Transcrição completa` (recolhível).

Requer o plugin **Dataview** (grátis) para a Central.

## 4. Tratamento de erros e resiliência

| Falha | Comportamento |
|---|---|
| Whisper falha | Mantém áudio em staging, marca `.error`, notifica no menu; reprocessa depois |
| Codex offline / limite do plano / erro | **Fallback automático para Ollama** |
| Ollama também indisponível | Cria nota **só com transcrição** (`resumido_por: nenhum`) p/ reprocessar |
| Ollama não rodando | Sobe `ollama serve` em background antes de usar |
| Sem espaço em disco | Aborta gravação e avisa |
| Reprocessamento | Idempotente por **hash do áudio** (não duplica nota) |
| Clipe acidental (<5s) | Descartado |

## 5. Privacidade e controles

- Toggle **"próxima gravação: só local"** → força `ollama`.
- **Lista de apps ignorados** (ex.: banco, apps pessoais) → nunca auto-grava.
- **"Descartar última"** → apaga áudio + nota da última gravação.
- **Pausar auto-detecção** (modo soneca).
- Com `codex`, apenas o **texto** da transcrição vai à OpenAI; áudio e transcrição
  bruta permanecem locais. Para conteúdo sensível, usar `ollama`/"só local".

## 6. Implementação em fases

1. **Áudio**: BlackHole + Aggregate/Multi-Output (setup único guiado) → ffmpeg grava arquivo válido.
2. **Processador**: pipeline transcrever → resumir → escrever nota, testado com 1 áudio de exemplo.
3. **Orquestrador (manual)**: Hammerspoon com atalho + barra de menu.
4. **Auto-detecção**: gatilho por microfone em uso + app-alvo.
5. **Refino**: Central Dataview, apps ignorados, descartar/soneca, modo "só local".

## 7. Testes

- **Unit (processor/summarizer)**: rodar com transcrição de exemplo → validar JSON e markdown gerado.
- **Detecção**: simular uso do mic por um app-alvo → confirmar start/stop.
- **E2E**: gravar 30s (nota e reunião), confirmar nota no vault com frontmatter correto e áudio arquivado.
- **Fallback**: forçar Codex indisponível → confirmar resumo via Ollama; forçar ambos → nota só-transcrição.

## 8. Questões em aberto (resolver no plano)

- Identificação de `origem=Meet` quando em navegador (best-effort por app/aba).
- Modelo Whisper ideal no M4 (qualidade × velocidade): `medium` vs `large-v3-turbo`.
- Extração de `participantes` (heurística via transcrição vs metadados do app).
- Linguagem do `orchestrator`: Hammerspoon (Lua) confirmado; glue em shell + Python.
