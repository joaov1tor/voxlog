# voxlog — Perfil de voz + diarização (identificar "Eu" nas reuniões)

> Design aprovado em 2026-06-21. **LOCAL-ONLY** (não vai pro voxlog público — referencia os
> áudios do WhatsApp e infra do avell; mesma regra de privacidade do subprojeto WhatsApp,
> ver [[voxlog-whatsapp-rotina]] / [[sempre-sincronizar-github]]).

## 1. Problema

As gravações de **reunião** do voxlog são **mic + áudio do sistema misturados num stream só** →
a transcrição não distingue quem falou. O usuário quer um **perfil da própria voz** para que a
transcrição **o identifique** ("Eu") no meio dos outros falantes. (Notas de voz, WhatsApp e o futuro
bot Discord NÃO precisam disso — já são de um único falante ou já vêm separados por pessoa.)

## 2. Decisões (aprovadas)

1. **Enrollment automático** a partir dos **6.820 áudios `is_from_me`** do WhatsApp corporativo
   (voz pura do usuário, já no avell) → embedding médio = `perfil_eu`.
2. **Diarização completa**: separa todos os falantes e rotula o que bate com `perfil_eu` como
   **"Eu"**, os demais como **"Falante 2/3…"**.
3. **Ferramenta: WhisperX + pyannote** (transcrição + alinhamento + diarização num passo), com
   **token HuggingFace** (pyannote é gated).
4. **Qualidade primeiro**: modelo `medium`, passos em sequência para caber na **RTX 3060 6GB**.
5. **Escopo:** só gravações de reunião (`tipo: reuniao`), **incluindo backfill** das reuniões já
   gravadas (re-diarizar os `.m4a` em `🎙️ Gravações/_audios/` e atualizar as notas).
6. Roda como **serviço no avell** (GPU); o voxlog roteia o áudio de reunião pra lá.

## 3. Ambiente (verificado)

- avell: **RTX 3060 Laptop 6GB**; `:5050` = `whisper-service` próprio com **faster-whisper**
  (`/home/jv/products/whisper-service/`). Falta instalar `torch`/`whisperx`/`pyannote.audio`.
- Banco WhatsApp: `/home/jv/.whatsapp-mcp/whatsapp-bridge/store/messages.db`
  (`media_type='audio' AND is_from_me=1` → 6.820 linhas). Mídia baixa sob demanda via REST do
  bridge (`POST http://localhost:8085/api/download`), igual à rotina WhatsApp.

## 4. Arquitetura

Tudo que precisa de GPU + perfil + áudios fica **no avell**; o voxlog cliente só envia o áudio de
reunião e recebe a transcrição **já rotulada**.

```
[Mac voxlog] grava reunião (mic+sistema)
   └─ tipo=reuniao → manda o .m4a pro serviço de diarização no avell  (em vez do :5050 puro)

[avell: serviço de diarização (WhisperX) :5051]
   1. WhisperX: transcreve (faster-whisper medium) + alinha por palavra + diariza (pyannote)
        → segmentos com falantes anônimos SPEAKER_00/01...
   2. para cada cluster de falante: calcula embedding (mesmo modelo do enrollment)
   3. compara (cosseno) ao perfil_eu.npy:
        - cluster acima do limiar → "Eu"
        - demais → "Falante 2/3..."
   4. devolve transcrição rotulada (linhas "Eu: ..." / "Falante 2: ...")
        ←──────────────────────────────────────────────
[Mac voxlog] resume (codex) + escreve nota com a transcrição rotulada
```

**Por que server-side completo:** o `perfil_eu`, os áudios de enrollment e a GPU estão no avell.
Fazer o match lá evita trafegar embeddings e mantém o cliente burro (só manda áudio, recebe texto).

## 5. Componentes

### 5.1. No avell (novo)

| Artefato | Responsabilidade |
|---|---|
| `setup/avell/whisperx-service/` | Serviço HTTP (`:5051`) tipo o whisper-service atual: recebe áudio → roda WhisperX (transcribe+align+diarize) → faz o match com `perfil_eu` → retorna JSON `{segments:[{speaker, start, end, text}], labeled_text}`. Carrega modelos uma vez (lazy), roda passos em sequência p/ caber em 6GB. |
| `scripts/voice_enroll.py` (roda no avell) | Lê N áudios `is_from_me` do `messages.db`, baixa via bridge REST, decodifica (ffmpeg → wav 16k mono), calcula embedding de cada um (mesmo modelo de speaker do serviço), salva a **mediana/centroide** em `~/.config/voxlog/perfil_eu.npy` + um `perfil_eu.json` (metadados: nº de amostras, modelo, data, limiar sugerido). |
| `requirements-avell-voz.txt` | `torch`, `whisperx`, `pyannote.audio` (pinados p/ CUDA da 3060). |

### 5.2. No voxlog (pacote Python — editar)

| Arquivo | Mudança |
|---|---|
| `src/voxlog/config.py` | Seção `[voice]`: `diarize_endpoint` (ex.: `http://localhost:5051`), `enabled` (bool), `perfil_path`, `match_threshold` (ex.: 0.5). |
| `src/voxlog/transcribe.py` | Nova função `transcribe_diarized(audio, cfg) -> str` que chama o `diarize_endpoint` e devolve a transcrição **rotulada**. Reusa o padrão `curl` injetável já existente. |
| `src/voxlog/process.py` | Para `tipo == "reuniao"` e `cfg.voice.enabled`, usar `transcribe_diarized`; senão, o `transcribe` normal (:5050). Notas de voz nunca diarizam. |
| `src/voxlog/vault.py` | A seção "📝 Transcrição completa" passa a renderizar as linhas já rotuladas (`Eu: …` / `Falante 2: …`) — quando vier diarizada. |
| `src/voxlog/cli.py` | `voxlog voice-status` (checa `perfil_eu` + saúde do `:5051`) e **`voxlog voice-backfill [--since DATA]`**. |
| `src/voxlog/voice_backfill.py` | Itera as notas `tipo: reuniao` do vault, acha o `.m4a` (via `audio_hash`/`audio:` no frontmatter) em `🎙️ Gravações/_audios/`, re-diariza no `:5051` e **substitui a seção "📝 Transcrição completa"** pela versão rotulada (idempotente: pula nota que já tem transcrição diarizada). Opcionalmente re-resume. |

## 6. Enrollment — detalhes

- **Amostragem:** pegar ~150–300 áudios `is_from_me` (não todos os 6.820 — média de ~200 já é
  robusta e barata), priorizando os de duração média (descartar < 1s e clipes muito longos).
- **Pipeline por áudio:** download (bridge) → ffmpeg p/ wav 16k mono → embedding (modelo de speaker).
- **Agregação:** centroide L2-normalizado (robusto a 1–2 áudios encaminhados que não sejam a voz do
  usuário). Guardar também o desvio p/ calibrar o limiar.
- **Idempotente / versionado:** `perfil_eu.json` registra data e nº de amostras; re-rodar substitui.

## 7. Matching — rótulo "Eu"

- O serviço calcula 1 embedding por cluster de falante da reunião (média dos segmentos do cluster).
- Similaridade de cosseno com `perfil_eu`. O cluster com maior similaridade **e** acima de
  `match_threshold` vira **"Eu"**; se nenhum passar, ninguém é marcado como Eu (melhor não errar).
- Demais clusters → "Falante 2", "Falante 3"… (ordem de aparição).
- **Mesmo modelo de embedding** no enrollment e no serviço (senão os vetores não são comparáveis).

## 8. Formato na nota

Frontmatter ganha `participantes` com "Eu" + nº de outros (o resumidor já extrai nomes citados). A
transcrição vira:

```markdown
## 📝 Transcrição completa

> [!quote]- Transcrição (diarizada)
> **Eu** [00:03]: bom dia pessoal, vamos começar...
> **Falante 2** [00:11]: ...
> **Eu** [00:25]: ...
```

(Quando não-diarizada — notas de voz, fallback — mantém o formato atual de bloco único.)

## 9. Erros / fallback

- Serviço `:5051` fora do ar ou sem `perfil_eu` → **cai para o `:5050` normal** (transcrição sem
  rótulo); a nota sai sem diarização em vez de falhar.
- pyannote falha (token HF inválido) → idem fallback + log claro.
- VRAM insuficiente num pico → o serviço roda os passos em sequência (transcreve, libera VRAM,
  diariza); se ainda assim faltar, diarização cai pra CPU (mais lento) — configurável.

## 10. Fora de escopo (de propósito)

- Identificar **outras pessoas** por nome (só "Eu" tem perfil; os demais são genéricos). Enroll de
  colegas é melhoria futura.
- Diarizar WhatsApp/Discord (já vêm por falante).
- Tempo real (é batch, pós-gravação).

## 11. Riscos / a verificar na implementação

1. **VRAM 6GB:** confirmar que `medium` (int8) + pyannote rodam em sequência sem OOM; medir tempo
   por minuto de reunião. Ter o fallback CPU pra diarização pronto.
2. **Token HF:** o usuário cria o token e aceita os termos de `pyannote/speaker-diarization-3.1`
   (e do modelo de segmentação). Guardar em `~/.config/voxlog/` (não versionar).
3. **Modelo de embedding consistente** entre `voice_enroll.py` e o serviço.
4. **Qualidade do enrollment:** alguns `is_from_me` podem ser áudios encaminhados (não a voz do
   usuário) — a agregação por centroide de ~200 amostras dilui; validar com uma reunião real.
5. **Rota do áudio Mac→avell:** hoje o Mac já manda áudio pro `:5050`; confirmar o mesmo caminho
   (HTTP) para o `:5051`.
