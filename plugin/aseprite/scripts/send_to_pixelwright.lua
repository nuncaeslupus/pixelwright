-- Save the active sprite as a new pixelwright draft version, with a history note.
-- Headless: aseprite -b sprite.aseprite --script-param asset=<id>
--   [--script-param note=...] [--script-param parent=v0003] [--script-param workspace=<dir>]
--   --script send_to_pixelwright.lua
local here = app.fs.filePath(debug.getinfo(1, "S").source:sub(2))
local pw = dofile(app.fs.joinPath(here, "pixelwright.lua"))

local sprite = app.sprite or app.activeSprite
if not sprite then return pw.fail("pixelwright: no active sprite") end
local p = pw.params({ "asset", "note", "parent", "workspace", "pw" }, "Send to pixelwright")
if not p then return end

local tmp = app.fs.joinPath(app.fs.tempPath, "pixelwright-send-" .. os.time() .. ".png")
sprite:saveCopyAs(tmp)
local args = { "attach", p.asset, tmp, "--note", p.note or "edited in Aseprite" }
if p.parent and p.parent ~= "" then
  args[#args + 1] = "--parent"
  args[#args + 1] = p.parent
end
local ok, result = pcall(pw.pw, args, p)
os.remove(tmp)
if not ok then return pw.fail(result) end
print("pixelwright: " .. result.asset .. " " .. result.version)
