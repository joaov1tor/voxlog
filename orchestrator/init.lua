-- voxlog orchestrator (Hammerspoon)
local REPO   = "/Volumes/SSD/Dropbox/Developments/gravador_audio"
local RECORD = REPO .. "/recorder/record.sh"
local VOXLOG = REPO .. "/.venv/bin/voxlog"
local STAGING = os.getenv("HOME") .. "/Gravacoes/staging"
local LOG = os.getenv("HOME") .. "/Gravacoes/voxlog.log"

local M = { task = nil, current_file = nil, current_tipo = nil, current_origem = nil, auto = false, auto_app = nil, indicator = nil }
local menubar = hs.menubar.new()

local function setIcon(recording)
  menubar:setTitle(recording and "🔴 voxlog" or "🎙️ voxlog")
end

-- Indicador permanente na tela enquanto grava (canto superior direito)
local function showIndicator(label)
  if M.indicator then M.indicator:delete() end
  local f = hs.screen.mainScreen():frame()
  local w, h = 230, 40
  M.indicator = hs.canvas.new({ x = f.x + f.w - w - 18, y = f.y + 18, w = w, h = h })
  M.indicator:appendElements(
    { type = "rectangle", action = "fill",
      roundedRectRadii = { xRadius = 10, yRadius = 10 },
      fillColor = { red = 0, green = 0, blue = 0, alpha = 0.78 } },
    { type = "circle", action = "fill", center = { x = 24, y = 20 }, radius = 7,
      fillColor = { red = 0.92, green = 0.12, blue = 0.12, alpha = 1 } },
    { type = "text", text = "GRAVANDO · " .. label,
      frame = { x = 40, y = 9, w = w - 46, h = 24 },
      textColor = { white = 1 }, textSize = 15 }
  )
  M.indicator:level(hs.canvas.windowLevels.overlay)
  M.indicator:show()
end

local function hideIndicator()
  if M.indicator then M.indicator:delete(); M.indicator = nil end
end

local function process(file, tipo, origem)
  if not file then return end
  -- roda via login shell (/bin/zsh -lc) p/ herdar o PATH completo do usuário
  -- (whisper/codex/ollama/ffprobe não estão no PATH mínimo do hs.task)
  -- PATH explícito: o `zsh -lc` do Hammerspoon não carrega o .zshrc (onde fica
  -- o conda), então o whisper do anaconda não era encontrado. Garante os bins.
  local cmd = string.format(
    "export PATH=\"$HOME/anaconda3/bin:/opt/homebrew/bin:/usr/local/bin:$PATH\"; %s process '%s' --tipo '%s' --origem '%s' >> '%s' 2>&1",
    VOXLOG, file, tipo, origem, LOG)
  hs.task.new("/bin/zsh", function(code, _, _)
    hs.notify.new({title="voxlog",
      informativeText=(code==0 and "Nota criada ✅" or "Falha — ver ~/Gravacoes/voxlog.log ❌")}):send()
  end, {"-lc", cmd}):start()
end

local function stopRecording()
  if not M.task then return end
  M.task:terminate()                 -- SIGTERM → ffmpeg finaliza o arquivo
  M.task = nil
  setIcon(false)
  hideIndicator()
  hs.alert.show("⏹ voxlog: gravação encerrada — processando…", 2)
  local f, t, o = M.current_file, M.current_tipo, M.current_origem
  M.current_file = nil
  hs.timer.doAfter(1.0, function() process(f, t, o) end)
end

local function startRecording(tipo, origem)
  if M.task then return end
  M.current_tipo, M.current_origem = tipo, origem
  M.task = hs.task.new("/bin/bash", function() end,
    function(_, stdout, _)            -- streaming callback: 1a linha = caminho
      if stdout and not M.current_file then
        M.current_file = stdout:match("^%s*([^\n]+)")
      end
      return true
    end,
    {RECORD, tipo, STAGING})
  M.current_file = nil
  M.task:start()
  setIcon(true)
  local label = (tipo == "reuniao") and ("reunião (" .. tostring(origem) .. ")") or "nota"
  showIndicator(label)
end

local function toggleNote()
  if M.task then stopRecording() else startRecording("nota", "manual") end
end

hs.hotkey.bind({"alt","cmd"}, "R", toggleNote)

-- ===== Auto-detecção de reunião =====
local TARGET_APPS = { "zoom.us", "Microsoft Teams", "com.microsoft.teams2", "Discord", "Google Chrome", "Safari", "Arc" }
local IGNORED_APPS = {}            -- ex.: { "Banco" }
M.paused = false

local function appRunning(name)
  return hs.application.find(name) ~= nil
end

local function activeTargetApp()
  for _, name in ipairs(IGNORED_APPS) do
    if appRunning(name) then return nil end
  end
  for _, name in ipairs(TARGET_APPS) do
    if appRunning(name) then return name end
  end
  return nil
end

local function micInUse()
  local dev = hs.audiodevice.defaultInputDevice()
  return dev and dev:inUse()
end

M.timer = hs.timer.new(3, function()
  if M.paused then return end
  local target = activeTargetApp()
  if (not M.task) and micInUse() and target then
    startRecording("reuniao", target)          -- auto-início
    M.auto = true
    M.auto_app = target
  elseif M.task and M.auto and M.auto_app and (not appRunning(M.auto_app)) then
    stopRecording()                              -- app saiu → fim da reunião
    M.auto = false
    M.auto_app = nil
  end
end)
M.timer:start()

-- itens de menu extras
menubar:setMenu(function()
  return {
    { title = M.task and "■ Parar gravação" or "● Gravar nota (⌥⌘R)", fn = toggleNote },
    { title = M.paused and "▶ Retomar auto-detecção" or "⏸ Pausar auto-detecção",
      fn = function() M.paused = not M.paused end },
    { title = "Abrir staging", fn = function() hs.execute("open " .. STAGING) end },
  }
end)
setIcon(false)

return M
