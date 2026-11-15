-- Open a pixelwright version (default: latest) in Aseprite.
-- Headless: aseprite -b --script-param asset=<id> [--script-param version=v0004]
--   [--script-param workspace=<dir>] --script load_version.lua
local here = app.fs.filePath(debug.getinfo(1, "S").source:sub(2))
local pw = dofile(app.fs.joinPath(here, "pixelwright.lua"))

local p = pw.params({ "asset", "version", "workspace", "pw" }, "Load pixelwright version")
if not p then return end
local args = { "render", p.asset, "--scale", "1" }
if p.version and p.version ~= "" then
  args[#args + 1] = "--version"
  args[#args + 1] = p.version
end
local ok, env = pcall(pw.pw, args, p)
if not ok then return pw.fail(env) end
local root = (p.workspace and p.workspace ~= "") and p.workspace or app.fs.currentPath
local sprite = app.open(app.fs.joinPath(root, env.data.source))
if not sprite then return pw.fail("pixelwright: could not open " .. env.data.source) end
print("pixelwright: opened " .. env.asset .. " " .. env.version)
