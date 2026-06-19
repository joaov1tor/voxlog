# Orchestrator (Hammerspoon)

1. Instalar Hammerspoon: `brew install --cask hammerspoon` e abrir uma vez (dar permissões de Acessibilidade).
2. Linkar este módulo no `~/.hammerspoon/init.lua`:
   ```bash
   mkdir -p ~/.hammerspoon
   echo 'dofile(os.getenv("HOME").."/Dropbox/Developments/gravador_audio/orchestrator/init.lua")' >> ~/.hammerspoon/init.lua
   ```
3. Em Hammerspoon → **Reload Config**.
4. Testar: `⌥⌘R` inicia/para uma nota; o ícone vira 🔴 enquanto grava.
