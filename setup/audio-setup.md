# Setup de áudio (one-time) — BlackHole + Aggregate Device

Necessário para o ffmpeg capturar **mic + áudio do sistema** juntos.

## 1. Instalar BlackHole 2ch
```bash
brew install blackhole-2ch
```
(Reiniciar o CoreAudio se não aparecer: `sudo killall coreaudiod`)

## 2. Audio MIDI Setup → criar dois dispositivos

Abrir **Audio MIDI Setup** (`/System/Applications/Utilities/Audio MIDI Setup.app`).

### a) Multi-Output Device (para CONTINUAR ouvindo)
- `+` → **Create Multi-Output Device**
- Marcar: **MacBook Pro Speakers** (ou seu headset) **+ BlackHole 2ch**
- Marcar **Drift Correction** na linha do BlackHole
- Renomear para `voxlog-MultiOut`
- A saída embutida deve ser a PRIMEIRA da lista

### b) Aggregate Device (para GRAVAR)
- `+` → **Create Aggregate Device**
- Marcar: **MacBook Pro Microphone** **+ BlackHole 2ch**
- Renomear para `voxlog-Aggregate`

## 3. Rotear o som do sistema
- **Ajustes do Sistema → Som → Saída** → selecionar `voxlog-MultiOut`
- Assim você ouve normalmente E o áudio vai pro BlackHole (que o Aggregate captura)

## 4. Permissões
- **Ajustes → Privacidade e Segurança → Microfone** → permitir Terminal/Hammerspoon

## 5. Verificar
```bash
ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | grep -i voxlog
```
Deve listar `voxlog-Aggregate` entre os dispositivos de áudio.
