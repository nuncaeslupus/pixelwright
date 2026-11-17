-- Open a version of a pixelwright asset (default: the latest).
-- Headless: aseprite -b --script-param asset=scenes/harbour [--script-param version=v003]
--   [--script-param workspace=<project dir>] [--script-param pw=<path to pw>]
local here = app.fs.filePath(debug.getinfo(1, "S").source:sub(2))
local pw = dofile(app.fs.joinPath(here, "pixelwright.lua"))

local p = pw.params({ "asset", "version", "workspace", "pw" }, "Load pixelwright version")
if not p then return end
local version = p.version
if not version or version == "" then
  local ok, env = pcall(pw.pw, { "status", p.asset }, p)
  if not ok then return pw.fail(env) end
  version = env.version
end
if not version or version == "" then return pw.fail("pixelwright: " .. p.asset .. " has no version") end
local root = (p.workspace and p.workspace ~= "") and p.workspace or app.fs.currentPath
local file = app.fs.joinPath(root, "assets", p.asset, "versions", version .. ".png")
local sprite = app.open(file)
if not sprite then return pw.fail("pixelwright: could not open " .. file) end
print("pixelwright: opened " .. p.asset .. " " .. version)
