const assert = require("assert")
const fs = require("fs")
const vm = require("vm")
const path = require("path")

const file = path.join(__dirname, "../ThemeCursorMappings.js")
const source = fs.readFileSync(file, "utf8").replace(/^\.pragma library\s*/, "")
const sandbox = { module: { exports: {} }, console }
vm.runInNewContext(source, sandbox, { filename: "ThemeCursorMappings.js" })
const Mappings = sandbox.module.exports

console.log("Running mappings tests...")

// Test normalization
assert.strictEqual(Mappings.normalizeOmarchyThemeId("Catppuccin Mocha"), "catppuccin-mocha")
assert.strictEqual(Mappings.normalizeOmarchyThemeId("Tokyo Night"), "tokyo-night")
assert.strictEqual(Mappings.normalizeOmarchyThemeId("rose_pine"), "rose-pine")
assert.strictEqual(Mappings.normalizeOmarchyThemeId("Nord"), "nord")
assert.strictEqual(Mappings.normalizeOmarchyThemeId("  AME Quattro  "), "ame-quattro")

// Test title formatting
assert.strictEqual(Mappings.formatOmarchyThemeName("catppuccin-mocha"), "Catppuccin Mocha")
assert.strictEqual(Mappings.formatOmarchyThemeName("tokyo-night"), "Tokyo Night")
assert.strictEqual(Mappings.formatOmarchyThemeName("nord"), "Nord")

const mockThemes = [
  { displayName: "Adwaita", hyprcursor: "Adwaita", xcursor: "Adwaita" },
  { displayName: "Banana", hyprcursor: "Banana", xcursor: "Banana" },
  { displayName: "Bibata-Catppuccin-Mocha", hyprcursor: "Bibata-Catppuccin-Mocha", xcursor: "Bibata-Catppuccin-Mocha" },
  { displayName: "Nordzy", hyprcursor: "Nordzy", xcursor: "Nordzy" },
  { displayName: "Custom-Imported", hyprcursor: "Custom-Imported", xcursor: "Custom-Imported" }
]

// 1. Default mapping resolution
let res = Mappings.resolveMappedTheme("catppuccin", {}, mockThemes)
assert.strictEqual(res.source, "default")
assert.strictEqual(res.theme.displayName, "Bibata-Catppuccin-Mocha")

res = Mappings.resolveMappedTheme("nord", {}, mockThemes)
assert.strictEqual(res.source, "default")
assert.strictEqual(res.theme.displayName, "Nordzy")

// 2. User mapping override
const userMappings = {
  "catppuccin": "Banana",
  "tokyo-night": "Custom-Imported"
}

res = Mappings.resolveMappedTheme("catppuccin", userMappings, mockThemes)
assert.strictEqual(res.source, "user")
assert.strictEqual(res.theme.displayName, "Banana")

res = Mappings.resolveMappedTheme("tokyo-night", userMappings, mockThemes)
assert.strictEqual(res.source, "user")
assert.strictEqual(res.theme.displayName, "Custom-Imported")

// 3. Unmatched theme falls back to Adwaita / default fallback
res = Mappings.resolveMappedTheme("completely-unknown-theme", {}, mockThemes)
assert.strictEqual(res.source, "fallback")
assert.strictEqual(res.theme.displayName, "Adwaita")

// 4. Missing mapped theme falls back safely
const brokenMappings = { "nord": "DeletedTheme" }
res = Mappings.resolveMappedTheme("nord", brokenMappings, mockThemes)
assert.strictEqual(res.source, "fallback")
assert.strictEqual(res.theme.displayName, "Adwaita")

console.log("mappings tests: ok")
