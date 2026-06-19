-- voxlog orchestrator (Hammerspoon)
local REPO   = os.getenv("HOME") .. "/Dropbox/Developments/gravador_audio"
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
  hs.timer.doAfter(1.0, function()
    process(M.current_file, M.current_tipo, M.current_origem)
  end)
end

local function startRecording(tipo, origem)
  if M.task then return end
  M.current_tipo, M.current_origem = tipo, origem
  M.task = hs.task.new("/bin/bash", function() end,
    function(_, stdout, _)            -- streaming callback: 1a linha = caminho
      if stdout and not M.current_file then
        M.current_file = stdout:gsub("%s+$", "")
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

menubar:setMenu(function()
  return {
    { title = M.task and "■ Parar gravação" or "● Gravar nota (⌥⌘R)", fn = toggleNote },
    { title = "Abrir staging", fn = function() hs.execute("open " .. STAGING) end },
  }
end)
setIcon(false)

return M
