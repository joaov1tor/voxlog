-- voxlog orchestrator (Hammerspoon)
local REPO   = "/Volumes/SSD/Dropbox/Developments/gravador_audio"
local RECORD = REPO .. "/recorder/record.sh"
local VOXLOG = REPO .. "/.venv/bin/voxlog"
local STAGING = "/Volumes/SSD/Gravacoes/staging"   -- SSD externo (Mac com pouco disco)
local LOG = "/Volumes/SSD/Gravacoes/voxlog.log"

local M = { task = nil, current_file = nil, current_tipo = nil, current_origem = nil, auto = false, auto_app = nil, indicator = nil, prompted = false, rec_app = nil, mic_free_ticks = 0 }
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
    function(_, stdout, _)            -- streaming callback: 1a linha = session id
      if stdout and not M.current_file then
        M.current_file = stdout:match("^%s*([^\n]+)")
      end
      return true
    end,
    {RECORD, tipo, STAGING})
  M.current_file = nil
  M.task:start()
  setIcon(true)
  M.mic_free_ticks = 0
  local label = (tipo == "reuniao") and ("reunião (" .. tostring(origem) .. ")") or "nota"
  showIndicator(label)
  -- alerta on-screen grande e mais longo (não depende de permissão de Notificações)
  hs.alert.show("🔴 GRAVANDO " .. string.upper(label) .. "\n⌥⌘R para parar",
                { textSize = 26, radius = 14, strokeWidth = 0,
                  fillColor = { red = 0.85, green = 0.1, blue = 0.1, alpha = 0.92 },
                  textColor = { white = 1 } }, 5)
end

local function toggleNote()
  if M.task then stopRecording() else startRecording("nota", "manual") end
end

hs.hotkey.bind({"alt","cmd"}, "R", toggleNote)

-- ===== Auto-detecção de reunião =====
local TARGET_APPS = { "zoom.us", "Microsoft Teams", "com.microsoft.teams2", "Discord", "Google Chrome", "Safari", "Arc" }
local IGNORED_APPS = {}            -- ex.: { "Banco" }
M.paused = false

-- ===== Janela de horário (seg-sex 8-18) =====
local ACTIVE_DAYS = { [2]=true, [3]=true, [4]=true, [5]=true, [6]=true } -- wday: 1=dom..7=sab
local ACTIVE_START, ACTIVE_END = 8, 18
local PRESENCIAL_DAYS = { [3]=true, [5]=true }   -- ter, qui
local PRESENCIAL_REMINDER_MIN = 60

local function in_window()
  local t = os.date("*t")
  return ACTIVE_DAYS[t.wday] and t.hour >= ACTIVE_START and t.hour < ACTIVE_END
end

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
  -- alerta on-screen (visível mesmo sem permissão de Notificações do Hammerspoon)
  hs.alert.show("🎙️ voxlog: reunião detectada (" .. app .. ") — ⌥⌘R para gravar", 6)
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

M.timer = hs.timer.new(3, function()
  if M.paused or not in_window() then return end
  local target = activeTargetApp()
  if (not M.task) and micInUse() and target then
    -- AUTO-INICIA ao detectar reunião: mic em uso + app de reunião + janela de
    -- horário. O "mic em uso" é sinal confiável de call ativa (fica false fora
    -- de call). Sem perguntar — o usuário pode parar com ⌥⌘R. Clipes curtos
    -- (falso-positivo) são descartados por min_duration_sec.
    startRecording("reuniao", target)
    M.auto = true; M.auto_app = target; M.rec_app = target
  elseif M.task then
    -- captura o app de reunião presente (p/ auto-stop), inclusive em gravação manual
    if not M.rec_app then M.rec_app = target end
    if M.rec_app and not appRunning(M.rec_app) then
      stopRecording()                            -- app de reunião saiu → fim
      M.rec_app = nil; M.auto = false; M.auto_app = nil; M.prompted = false; M.mic_free_ticks = 0
    elseif not micInUse() then
      M.mic_free_ticks = (M.mic_free_ticks or 0) + 1
      if M.mic_free_ticks >= 20 then             -- ~60s de mic livre → fim da call
        stopRecording()
        M.rec_app = nil; M.auto = false; M.auto_app = nil; M.prompted = false; M.mic_free_ticks = 0
      end
    else
      M.mic_free_ticks = 0
    end
  elseif (not M.task) and (not micInUse()) then
    M.prompted = false   -- mic livre: pode perguntar de novo na próxima reunião
  end
end)

-- ===== Reconciliação no boot (H1) =====
-- Em reload/crash, o ffmpeg (record.sh) continua vivo mas M.task se perde →
-- gravações órfãs e ffmpegs zumbis. No load: mata ffmpeg órfão e processa os
-- segmentos pendentes do staging (não perde a gravação).
local function reconcileOnBoot()
  hs.execute("/usr/bin/pkill -f avfoundation >/dev/null 2>&1")
  hs.timer.doAfter(2.5, function()                 -- deixa o ffmpeg finalizar os segmentos
    if not hs.fs.attributes(STAGING) then return end
    local seen = {}
    for file in hs.fs.dir(STAGING) do
      local sid = file:match("^(.+)_%d%d%d%.m4a$")
      if sid and not seen[sid] then
        seen[sid] = true
        local tipo = sid:match("_(%a+)$") or "nota"
        process(sid, tipo, "recuperado")
      end
    end
  end)
end
reconcileOnBoot()

M.timer:start()

-- ===== Lembrete presencial (Ter/Qui) =====
M.reminder_timer = hs.timer.new(PRESENCIAL_REMINDER_MIN * 60, function()
  local t = os.date("*t")
  if PRESENCIAL_DAYS[t.wday] and in_window() and not M.task then
    hs.notify.new({title = "voxlog",
      informativeText = "📍 Dia de TOTVS — grave reuniões presenciais com ⌥⌘R"}):send()
  end
end)
M.reminder_timer:start()

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
