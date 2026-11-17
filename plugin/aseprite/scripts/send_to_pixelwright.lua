-- Save the active sprite as a new version of a pixelwright asset (as is, no clean-up).
-- Headless: aseprite -b <file> --script-param asset=scenes/harbour
--   [--script-param workspace=<project dir>] [--script-param pw=<path to pw>]
local here = app.fs.filePath(debug.getinfo(1, "S").source:sub(2))
local pw = dofile(app.fs.joinPath(here, "pixelwright.lua"))

local sprite = app.sprite
if not sprite then return pw.fail("pixelwright: no active sprite") end
local p = pw.params({ "asset", "workspace", "pw" }, "Send to pixelwright")
if not p then return end

local tmp = app.fs.joinPath(app.fs.tempPath, "pixelwright-send-" .. os.time() .. ".png")
sprite:saveCopyAs(tmp)
local ok, result = pcall(pw.pw, { "add", p.asset, "--from", tmp, "--as-version" }, p)
os.remove(tmp)
if not ok then return pw.fail(result) end
print("pixelwright: " .. result.asset .. " " .. result.version)
