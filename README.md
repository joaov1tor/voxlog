# voxlog

Captura híbrida de áudio no Mac — registra **tudo que você fala** (notas de voz e reuniões) e organiza por **momento** e **assunto** no Obsidian, com transcrição local e resumo por IA.

> Status: 🚧 em design (brainstorm). Veja `docs/superpowers/specs/`.

## O que faz

- **Captura híbrida**
  - **Manual**: atalho global / barra de menu para gravar uma nota ou ideia.
  - **Automática**: detecta quando uma reunião começa (microfone em uso por Zoom, Teams, Meet ou Discord) e grava sozinho.
- **Mic + áudio do sistema** juntos (sua voz + o que os outros falam na call), via BlackHole + Aggregate Device.
- **Transcrição local** com Whisper (PT + EN), 100% no seu Mac.
- **Resumo + classificação por assunto** com backend plugável:
  - `codex` (padrão) — melhor qualidade, usa a assinatura ChatGPT/Codex.
  - `ollama` (fallback) — 100% local, para quando offline, no limite do plano, ou reuniões marcadas como privadas.
- **Organização no Obsidian**: cada gravação vira uma nota (= um momento) com frontmatter (tipo, data, origem, assunto, tags, participantes) e uma Central (Dataview) que agrupa por dia e por assunto.

## Arquitetura (resumo)

```
Hammerspoon (detecção + atalho + menu)
   → ffmpeg grava Aggregate Device (mic + sistema)
      → Whisper transcreve (local)
         → Codex/Ollama resume + classifica
            → nota .md no vault do Obsidian
```

## Ambiente alvo

- MacBook Pro M4, macOS 15.1
- Vault Obsidian: `SecundBrain`
- Stack local já presente: Whisper, Ollama, ffmpeg, Codex CLI

## Stack

- **Orquestração**: Hammerspoon (Lua)
- **Captura**: ffmpeg + BlackHole (Aggregate Device)
- **Transcrição**: openai-whisper (local)
- **Resumo**: Codex CLI (`codex exec`) com fallback Ollama (`llama3.1`)
- **Saída**: Markdown no Obsidian + Dataview

## Privacidade

Áudio e transcrição ficam no seu Mac. Com o backend `codex`, **o texto da transcrição é enviado à OpenAI** para gerar o resumo; use `ollama` (ou a marcação "só local") para conteúdo sensível.
