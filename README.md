# voxlog 🎙️

Grava **tudo que você fala** no Mac — notas de voz e reuniões (Zoom, Teams, Meet, Discord ou presencial) — captura **sua voz + o áudio do sistema** juntos, transcreve e organiza tudo em **notas no Obsidian** com resumo por IA. Estilo Notion AI Meeting Notes, mas seu, local e configurável.

> **Só Mac** (macOS 13+; testado no 15 / Apple Silicon).

## Instalação

Requer **Python 3.11+**. O voxlog não tem dependências de terceiros — instala e roda.

```bash
# com uv (recomendado)
uv tool install git+https://github.com/joaov1tor/voxlog

# ou com pipx
pipx install git+https://github.com/joaov1tor/voxlog
```

Depois, crie sua configuração:

```bash
voxlog init
```

O `init` pergunta onde fica seu vault do Obsidian, o idioma do áudio e qual resumidor usar,
e grava tudo em `~/.config/voxlog/voxlog.toml`. Nada é escrito fora daí.

### Atualizar

```bash
voxlog update
```

O voxlog também avisa sozinho, em uma linha, quando existe versão nova (checagem uma vez
por dia, em segundo plano). Para silenciar — útil em cron/launchd — defina
`VOXLOG_NO_UPDATE_CHECK=1`.

## Como funciona

```
Hammerspoon (atalho ⌥⌘R + auto-detecção de reunião + popup "gravar?")
   → ffmpeg grava mic + áudio do sistema (em segmentos)
      → Whisper transcreve (local OU GPU/web)
         → LLM resume e classifica (Codex / Ollama / ...)
            → nota .md no seu vault do Obsidian (resumo, itens de ação, tags, transcrição)
```

Pipeline completo em segundos por gravação; transcrição e resumo podem rodar fora do Mac (web/GPU) pra não pesar a máquina.

---

## 1. Instale os apps/dependências

```bash
# Homebrew (se não tiver): https://brew.sh
brew install ffmpeg blackhole-2ch                 # áudio
brew install --cask hammerspoon                   # orquestrador (atalho/popup/auto)
brew install --cask obsidian                       # destino das notas (ou já tenha)
pip install -U openai-whisper                       # transcrição LOCAL (fallback)
# Resumo: escolha um (veja a seção 5):
npm install -g @openai/codex                        # opção Codex (grátis c/ assinatura ChatGPT)
brew install ollama                                 # opção local (Ollama)
```

## 2. Clone e instale o voxlog

```bash
git clone git@github.com:joaov1tor/voxlog.git
cd voxlog
python3 -m venv .venv && ./.venv/bin/pip install -e .
```

## 3. Configure o áudio (mic + sistema) — passo único

Como o macOS não deixa apps capturarem o som do sistema direto, usamos o **BlackHole** + dois dispositivos no **Audio MIDI Setup**. Guia detalhado: [`setup/audio-setup.md`](setup/audio-setup.md). Resumo:

1. **`voxlog-Aggregate`** (Create Aggregate Device): marque **seu microfone** + **BlackHole 2ch**. É o que grava (mic + sistema).
2. **`voxlog-MultiOut`** (Create Multi-Output Device): marque **seus alto-falantes/fone** + **BlackHole 2ch** (Drift Correction no BlackHole). É pra você continuar ouvindo.
3. **Ajustes → Som → Saída = `voxlog-MultiOut`**; **Entrada = seu microfone**.

> Os nomes precisam ser exatamente `voxlog-Aggregate` e `voxlog-MultiOut`.

## 4. Configure o voxlog

```bash
mkdir -p ~/.config/voxlog
cp config/voxlog.toml.example ~/.config/voxlog/voxlog.toml
# edite ~/.config/voxlog/voxlog.toml: vault_path, staging_dir, whisper e summarizer
```

## 5. Escolha transcrição e resumo

### Transcrição (Whisper) — `whisper_model` / `whisper_endpoint`
- **Local (grátis):** deixe `whisper_endpoint = ""` e escolha o modelo em `whisper_model`: `tiny` < `base` < `small` < `medium` < `large-v3` (mais qualidade = mais lento/pesado no Mac).
- **Web/remoto (qualidade máxima, não pesa o Mac):** rode um Whisper numa GPU (ex.: `faster-whisper-server`/`speaches`, large-v3) ou use um provedor de mercado **compatível com a API OpenAI** (`/v1/audio/transcriptions`) e aponte `whisper_endpoint = "https://seu-servidor:porta"`. O voxlog faz upload do áudio e lê `{"text": ...}`. Se o remoto falhar, cai pro local automaticamente.

### Resumo (LLM) — `summarizer`
- **Codex** (`summarizer = "codex"`): usa o `codex` CLI (grátis com assinatura ChatGPT). Ótima qualidade, não usa RAM do Mac.
- **Ollama** (`summarizer = "ollama"`): 100% local/privado (`ollama_model`, ex. `llama3.1:8b`). Pesa o Mac (precisa de RAM).
- **Outras LLMs de mercado (Claude, OpenAI, Groq…):** o resumidor é **plugável** — qualquer backend que receba a transcrição e devolva o JSON `{resumo, assunto, tags, participantes, acoes}` serve. Claude (Anthropic) e OpenAI são suporte planejado; o padrão de backend está em `src/voxlog/summarize.py` (`_codex_cmd`/`_ollama_cmd`).

## 6. Ligue o Hammerspoon (atalho + automação)

1. Abra o **Hammerspoon**, conceda **Acessibilidade** e **Microfone**.
2. **Edite os caminhos no topo de `orchestrator/init.lua`** para a SUA máquina: `REPO` (pasta do clone), `STAGING`/`LOG`, e o `export PATH` (anaconda/nvm/homebrew, conforme onde estão seu `whisper`/`codex`).
3. Linke o módulo e recarregue:
   ```bash
   mkdir -p ~/.hammerspoon
   echo 'dofile("'$(pwd)'/orchestrator/init.lua")' >> ~/.hammerspoon/init.lua
   ```
   Hammerspoon → **Reload Config**. Deve aparecer 🎙️ voxlog na barra de menu.

## 7. Obsidian (painel)

Instale o plugin **Dataview** e copie [`vault-assets/_Central.md`](vault-assets/_Central.md) para a pasta `🎙️ Gravações/` do vault — vira um painel por dia/assunto. As notas linkam `[[assunto]]`, então o **grafo** agrupa as gravações por tema.

---

## Como usar no dia a dia

- **Nota de voz:** `⌥⌘R` (Option+Command+R) → fale → `⌥⌘R` de novo. Vira nota.
- **Reunião:** entre na call → o voxlog detecta e mostra um **popup "gravar?"** (estilo Notion) → clique **Gravar** (ou **Sempre neste app**). Para sozinho quando a call acaba.
- **Presencial:** use `⌥⌘R` (em dias configurados, há lembrete).
- **Reuniões longas:** gravadas em segmentos de ~20min e juntadas em **uma** nota.
- **Janela:** auto-detecção só seg–sex 8–18 (configurável no `init.lua`); o `⌥⌘R` manual funciona sempre.

## Personalização

Caminhos/horários a ajustar: `~/.config/voxlog/voxlog.toml` (vault, whisper, resumo, apps) e o topo de `orchestrator/init.lua` (`REPO`, `STAGING`, `LOG`, `PATH`, janela `ACTIVE_*`, lembrete `PRESENCIAL_*`, segmento `SEGMENT_SECONDS`).

## Problemas comuns

- **Gravação muda:** o app que grava precisa de permissão de **Microfone** (Hammerspoon, em Ajustes → Privacidade → Microfone). Sem ela, o macOS zera todo o áudio.
- **Não gera nota / erro:** veja o log em `<staging_dir>/../voxlog.log` (ex.: `~/voxlog/voxlog.log`).
- **`whisper`/`codex` não encontrados:** o Hammerspoon roda com PATH mínimo — garanta os diretórios certos no `export PATH` do `init.lua`.

## Stack

Hammerspoon (Lua) · ffmpeg + BlackHole · openai-whisper (local) ou Whisper-GPU/web (OpenAI-compat) · Codex/Ollama (resumo) · Obsidian + Dataview · Python (cola/CLI).

> Roadmap: captura nativa sem BlackHole (Core Audio taps) e backends de resumo Claude/OpenAI prontos. Contribuições bem-vindas.
