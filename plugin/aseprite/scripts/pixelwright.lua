-- Shared helpers for the pixelwright Aseprite scripts.
local M = {}

function M.quote(text)
  return "'" .. tostring(text):gsub("'", "'\\''") .. "'"
end

-- Run `pw <args> --json` and return the decoded envelope (errors raise).
function M.pw(args, params)
  local parts = { params.pw or "pw" }
  for _, a in ipairs(args) do parts[#parts + 1] = M.quote(a) end
  if params.workspace and params.workspace ~= "" then
    parts[#parts + 1] = "--workspace " .. M.quote(params.workspace)
  end
  parts[#parts + 1] = "--json"
  local handle = assert(io.popen(table.concat(parts, " ")))
  local out = handle:read("a")
  handle:close()
  local ok, env = pcall(json.decode, out)
  if not ok or type(env) ~= "table" then
    error("pw returned no JSON envelope: " .. tostring(out))
  end
  if not env.ok then
    error("pw " .. args[1] .. ": " .. env.error.code .. ": " .. env.error.message)
  end
  return env
end

-- Script parameters (headless) or a small dialog (GUI) for the missing ones.
function M.params(names, title)
  local values = {}
  local missing = false
  for _, name in ipairs(names) do
    values[name] = app.params[name]
    if (values[name] == nil or values[name] == "") and name ~= "note"
        and name ~= "version" and name ~= "workspace" and name ~= "pw" then
      missing = true
    end
  end
  if missing and app.isUIAvailable then
    local dlg = Dialog(title)
    for _, name in ipairs(names) do dlg:entry { id = name, label = name, text = values[name] or "" } end
    dlg:button { id = "ok", text = "OK" }:button { id = "cancel", text = "Cancel" }
    dlg:show()
    if not dlg.data.ok then return nil end
    for _, name in ipairs(names) do values[name] = dlg.data[name] end
  end
  return values
end

function M.fail(message)
  if app.isUIAvailable then app.alert(message) else print(message) end
end

return M
