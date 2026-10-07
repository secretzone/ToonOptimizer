-- ToonOptimizer: saves the SimulationCraft export of the current character to
-- SavedVariables so the ToonOptimizer app can import it without copy/paste.
local addonName, ns = ...

ns.version = "1.0.0"
local DB_VERSION = 1
local DEBOUNCE = 2
local FIRST_DELAY = 5
-- WoW writes SavedVariables only on /reload, logout or exit, and PLAYER_LOGOUT fires for all
-- three, so the logout capture is the one that lands on disk. Event captures are a fallback
-- and are spaced out so looting doesn't rebuild the export every few seconds.
local MIN_INTERVAL = 60

local frame = CreateFrame("Frame")
local pending = false      -- a debounced capture is scheduled
local waitingRegen = false -- capture deferred until combat ends
local firstWorld = true
local lastAuto = 0

local function say(msg)
  print("|cff33ccffToonOptimizer|r: " .. msg)
end

local function initDB()
  ToonOptimizerDB = type(ToonOptimizerDB) == "table" and ToonOptimizerDB or {}
  local db = ToonOptimizerDB
  db.version = DB_VERSION
  if type(db.settings) ~= "table" then db.settings = {} end
  if db.settings.auto == nil then db.settings.auto = true end
  if type(db.characters) ~= "table" then db.characters = {} end
  return db
end

-- Realm as the SimC export names it (server= line), falling back to the game's realm.
local function realmFromSimc(simc)
  local server = simc:match("\nserver=([^\r\n]+)") or simc:match("^server=([^\r\n]+)")
  if server and server ~= "" then return server end
  return (GetNormalizedRealmName and GetNormalizedRealmName()) or GetRealmName()
end

local function specName()
  local idx = C_SpecializationInfo and C_SpecializationInfo.GetSpecialization and C_SpecializationInfo.GetSpecialization()
  if idx then
    local _, name = C_SpecializationInfo.GetSpecializationInfo(idx)
    return name
  end
end

local function equippedIlvl()
  local _, equipped = GetAverageItemLevel()
  if not equipped then return nil end
  return math.floor(equipped * 10 + 0.5) / 10
end

-- Returns ok, info. info is the character key on success, or a reason string.
function ns.Capture()
  local api = _G.SimulationcraftAPI
  if not api or not api.GetSimcProfile then
    return false, "SimulationCraft addon API not found (is the Simulationcraft addon installed and enabled?)"
  end
  local ok, simc, err = pcall(api.GetSimcProfile, nil, false, false, false, nil)
  if not ok then return false, "SimulationCraft error: " .. tostring(simc) end
  if err or type(simc) ~= "string" or simc == "" then
    return false, err and tostring(err) or "empty SimulationCraft export"
  end

  local db = ToonOptimizerDB or initDB()
  local name = UnitName("player")
  local realm = GetRealmName()
  local key = name .. "-" .. realmFromSimc(simc)
  local _, class = UnitClass("player")
  db.characters[key] = {
    simc = simc,
    captured_at = time(),
    name = name,
    realm = realm,
    class = class,
    spec = specName(),
    ilvl = equippedIlvl(),
    addon_version = ns.version,
  }
  return true, key
end

local function autoCapture()
  pending = false
  if not (ToonOptimizerDB and ToonOptimizerDB.settings.auto) then return end
  if InCombatLockdown() then
    waitingRegen = true
    frame:RegisterEvent("PLAYER_REGEN_ENABLED")
    return
  end
  lastAuto = GetTime()
  pcall(ns.Capture)
end

local function schedule(delay)
  if pending then return end
  pending = true
  local wait = math.max(delay or DEBOUNCE, MIN_INTERVAL - (GetTime() - lastAuto))
  C_Timer.After(wait, autoCapture)
end

frame:SetScript("OnEvent", function(_, event, arg1)
  if event == "ADDON_LOADED" then
    if arg1 == addonName then
      initDB()
      frame:UnregisterEvent("ADDON_LOADED")
    end
  elseif event == "PLAYER_ENTERING_WORLD" then
    if firstWorld then
      firstWorld = false
      schedule(FIRST_DELAY)
    else
      schedule()
    end
  elseif event == "PLAYER_REGEN_ENABLED" then
    frame:UnregisterEvent("PLAYER_REGEN_ENABLED")
    if waitingRegen then
      waitingRegen = false
      schedule()
    end
  elseif event == "PLAYER_LOGOUT" then
    if ToonOptimizerDB and ToonOptimizerDB.settings.auto then pcall(ns.Capture) end
  else
    schedule()
  end
end)

frame:RegisterEvent("ADDON_LOADED")
for _, e in ipairs({
  "PLAYER_ENTERING_WORLD", "PLAYER_EQUIPMENT_CHANGED", "TRAIT_CONFIG_UPDATED",
  "ACTIVE_PLAYER_SPECIALIZATION_CHANGED", "BAG_UPDATE_DELAYED", "WEEKLY_REWARDS_UPDATE",
  "PLAYER_LOGOUT",
}) do
  frame:RegisterEvent(e)
end

local function slash(msg)
  local arg = strtrim(msg or ""):lower()
  local db = ToonOptimizerDB or initDB()
  if arg == "on" or arg == "off" then
    db.settings.auto = (arg == "on")
    say("auto capture " .. arg)
  elseif arg == "status" then
    local name = UnitName("player")
    local found
    for key, c in pairs(db.characters) do
      if c.name == name then
        say(("%s last captured %s"):format(key, date("%Y-%m-%d %H:%M:%S", c.captured_at)))
        found = true
      end
    end
    if not found then say("no capture yet for " .. tostring(name)) end
    say("auto capture is " .. (db.settings.auto and "on" or "off"))
  else
    local ok, info = ns.Capture()
    if ok then
      say("Saved " .. UnitName("player") .. ". /reload or log out so ToonOptimizer can read it.")
    else
      say("Could not save: " .. tostring(info))
    end
  end
end

SLASH_TOONOPTIMIZER1 = "/topt"
SLASH_TOONOPTIMIZER2 = "/toonopt"
SlashCmdList.TOONOPTIMIZER = slash
