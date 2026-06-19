-- voxlog orchestrator (Hammerspoon)
local REPO   = "/Volumes/SSD/Dropbox/Developments/gravador_audio"
local RECORD = REPO .. "/recorder/record.sh"
local VOXLOG = REPO .. "/.venv/bin/voxlog"
local STAGING = os.getenv("HOME") .. "/Gravacoes/staging"

local M = { task = nil, current_file = nil, current_tipo = nil, current_origem = nil }
local menubar = hs.menubar.new()

local function setIcon(recording)
  menubar:setTitle(recording and "🔴 voxlog" or "🎙️ voxlog")
end

local function process(file, tipo, origem)
  if not file then return end
  hs.task.new(VOXLOG, function(code, out, err)
    hs.notify.new({title="voxlog", informativeText=(code==0 and "Nota criada" or "Falha ao processar")}):send()
  end, {"process", file, "--tipo", tipo, "--origem", origem}):start()
end

local function stopRecording()
  if not M.task then return end
  M.task:terminate()                 -- SIGTERM → ffmpeg finaliza o arquivo
  M.task = nil
  setIcon(false)
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
end

local function toggleNote()
  if M.task then stopRecording() else startRecording("nota", "manual") end
end

hs.hotkey.bind({"alt","cmd"}, "R", toggleNote)

-- ===== Auto-detecção de reunião =====
local TARGET_APPS = { "zoom.us", "Microsoft Teams", "Discord", "Google Chrome", "Safari", "Arc" }
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

hs.timer.new(3, function()
  if M.paused then return end
  local target = activeTargetApp()
  if (not M.task) and micInUse() and target then
    startRecording("reuniao", target)          -- auto-início
    M.auto = true
  elseif M.task and M.auto and (not micInUse()) then
    stopRecording()                              -- mic liberado → fim da reunião
    M.auto = false
  end
end):start()

-- itens de menu extras
local baseMenu = menubar
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
