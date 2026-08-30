const assert = require("assert")
const fs = require("fs")
const vm = require("vm")

const source = fs.readFileSync("CursorModel.js", "utf8").replace(/^\.pragma library\s*/, "")
const sandbox = { module: { exports: {} }, console }
vm.runInNewContext(source, sandbox, { filename: "CursorModel.js" })
const Model = sandbox.module.exports

// Supported sizes and default fallback
const expectedSizes = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]
assert.deepStrictEqual(Array.from(Model.SupportedSizes), expectedSizes)
assert.strictEqual(Model.DefaultSize, 16)
assert.strictEqual(Model.validSize(32), 32)
assert.strictEqual(Model.validSize(256), 256)
assert.strictEqual(Model.validSize(33), 16) // fallback to 16
assert.strictEqual(Model.validSize(250), 16) // fallback to 16
assert.strictEqual(Model.validSize("16"), 16)
assert.strictEqual(Model.validSize(undefined), 16)
assert.strictEqual(Model.validSize(null), 16)
assert.strictEqual(Model.validSize(33, 24), 24) // custom fallback

// Stepper navigation tests
assert.strictEqual(Model.nextSize(16), 20)
assert.strictEqual(Model.nextSize(20), 24)
assert.strictEqual(Model.nextSize(24), 28)
assert.strictEqual(Model.nextSize(28), 32)
assert.strictEqual(Model.nextSize(32), 40)
assert.strictEqual(Model.nextSize(40), 48)
assert.strictEqual(Model.nextSize(48), 64)
assert.strictEqual(Model.nextSize(64), 80)
assert.strictEqual(Model.nextSize(80), 96)
assert.strictEqual(Model.nextSize(96), 128)
assert.strictEqual(Model.nextSize(128), 160)
assert.strictEqual(Model.nextSize(160), 192)
assert.strictEqual(Model.nextSize(192), 224)
assert.strictEqual(Model.nextSize(224), 256)
// 256 -> 256 (no wrap)
assert.strictEqual(Model.nextSize(256), 256)

// Decrement step transitions
assert.strictEqual(Model.prevSize(256), 224)
assert.strictEqual(Model.prevSize(224), 192)
assert.strictEqual(Model.prevSize(192), 160)
assert.strictEqual(Model.prevSize(160), 128)
assert.strictEqual(Model.prevSize(128), 96)
assert.strictEqual(Model.prevSize(96), 80)
assert.strictEqual(Model.prevSize(80), 64)
assert.strictEqual(Model.prevSize(64), 48)
assert.strictEqual(Model.prevSize(48), 40)
assert.strictEqual(Model.prevSize(40), 32)
assert.strictEqual(Model.prevSize(32), 28)
assert.strictEqual(Model.prevSize(28), 24)
assert.strictEqual(Model.prevSize(24), 20)
assert.strictEqual(Model.prevSize(20), 16)

// Minus is disabled at 16
assert.strictEqual(Model.canDecreaseSize(16), false)
assert.strictEqual(Model.prevSize(16), 16) // no wrap

// Plus is disabled at 256
assert.strictEqual(Model.canIncreaseSize(256), false)
assert.strictEqual(Model.nextSize(256), 256) // no wrap

// Bounds checking
assert.strictEqual(Model.canDecreaseSize(20), true)
assert.strictEqual(Model.canIncreaseSize(40), true)
assert.strictEqual(Model.canIncreaseSize(16), true)
assert.strictEqual(Model.canIncreaseSize(224), true)
assert.strictEqual(Model.canDecreaseSize(256), true)

// VisibleThemes allowlist validation
const expectedVisible = [
  "Banana",
  "Banana-Catppuccin-Mocha",
  "Banana-Green",
  "Adwaita",
  "Bibata-Catppuccin-Mocha",
  "Phinger",
  "Oreo",
  "Volantes",
  "Nordzy",
  "Capitaine"
]
assert.deepStrictEqual(Array.from(Model.VisibleThemes), expectedVisible)

const mockDiscovered = [
  { displayName: "Banana", hyprcursor: "Banana", xcursor: "Banana", formats: ["hyprcursor", "xcursor"], bundled: true, subtitle: "ful1e5" },
  { displayName: "Banana-Blue", hyprcursor: "", xcursor: "Banana-Blue", formats: ["xcursor"] },
  { displayName: "Banana-Catppuccin-Mocha", hyprcursor: "", xcursor: "Banana-Catppuccin-Mocha", formats: ["xcursor"], subtitle: "ful1e5" },
  { displayName: "Banana-Green", hyprcursor: "", xcursor: "Banana-Green", formats: ["xcursor"], subtitle: "ful1e5" },
  { displayName: "Adwaita", hyprcursor: "", xcursor: "Adwaita", formats: ["xcursor"] },
  { displayName: "Bibata-Catppuccin-Frappe", hyprcursor: "", xcursor: "Bibata-Catppuccin-Frappe", formats: ["xcursor"] },
  { displayName: "Bibata-Catppuccin-Latte", hyprcursor: "", xcursor: "Bibata-Catppuccin-Latte", formats: ["xcursor"] },
  { displayName: "Bibata-Catppuccin-Mocha", hyprcursor: "", xcursor: "Bibata-Catppuccin-Mocha", formats: ["xcursor"] },
  { displayName: "Phinger", hyprcursor: "Phinger", xcursor: "Phinger", formats: ["hyprcursor", "xcursor"], bundled: true, subtitle: "phisch" },
  { displayName: "Oreo", hyprcursor: "Oreo", xcursor: "Oreo", formats: ["hyprcursor", "xcursor"], bundled: true, subtitle: "varlesh" },
  { displayName: "Volantes", hyprcursor: "Volantes", xcursor: "Volantes", formats: ["hyprcursor", "xcursor"], bundled: true, subtitle: "varlesh" },
  { displayName: "Nordzy", hyprcursor: "Nordzy-cursors", xcursor: "Nordzy-cursors", formats: ["hyprcursor", "xcursor"], bundled: true, subtitle: "gboehm" },
  { displayName: "Capitaine", hyprcursor: "Capitaine", xcursor: "Capitaine", formats: ["hyprcursor", "xcursor"], bundled: true, subtitle: "Keefer Rourke" },
  { displayName: "Yaru", hyprcursor: "", xcursor: "Yaru", formats: ["xcursor"] },
  { displayName: "OtherUnknown", hyprcursor: "OtherUnknown", formats: ["hyprcursor"] }
]

const filtered = Model.normalizeThemes(mockDiscovered)
// 1. Exactly 10 themes are exposed
assert.strictEqual(filtered.length, 10)
// 2. Ordering is exact
assert.deepStrictEqual(Array.from(filtered.map(t => t.displayName)), expectedVisible)
// 3. Unlisted themes are filtered out
assert.strictEqual(filtered.some(t => t.displayName === "Banana-Dracula"), false)
assert.strictEqual(filtered.some(t => t.displayName === "Banana-Blue"), false)
assert.strictEqual(filtered.some(t => t.displayName === "Yaru"), false)
assert.strictEqual(filtered.some(t => t.displayName === "OtherUnknown"), false)

// 4. Fallback handling for persisted hidden/unlisted theme
assert.strictEqual(Model.findTheme(filtered, { displayName: "Banana-Dracula", xcursor: "Banana-Dracula" }), null)
assert.strictEqual(Model.fallbackTheme(filtered, "Banana-Dracula").displayName, "Banana")
assert.strictEqual(Model.fallbackTheme(filtered, "Banana-Green").displayName, "Banana-Green")
assert.strictEqual(Model.fallbackTheme(filtered, "Banana-Catppuccin-Mocha").displayName, "Banana-Catppuccin-Mocha")
assert.strictEqual(Model.fallbackTheme(filtered, "Nordzy").displayName, "Nordzy")

// 5. Grid navigation with 10 items across 3 columns
const columns = 3
function stepGrid(currentIndex, dx, dy) {
  let next = currentIndex
  if (dy !== 0) next += dy * columns
  else next += dx
  return Math.max(0, Math.min(filtered.length - 1, next))
}
// Row 0: 0 (Banana), 1 (Banana-Catppuccin-Mocha), 2 (Banana-Green)
// Row 1: 3 (Adwaita), 4 (Bibata-Catppuccin-Mocha), 5 (Phinger)
// Row 2: 6 (Oreo), 7 (Volantes), 8 (Nordzy)
// Row 3: 9 (Capitaine)
assert.strictEqual(stepGrid(2, 0, 1), 5) // down from 2 (Banana-Green) -> 5 (Phinger)
assert.strictEqual(stepGrid(5, 0, 1), 8) // down from 5 (Phinger) -> 8 (Nordzy)
assert.strictEqual(stepGrid(8, 0, 1), 9) // down from 8 (Nordzy) -> clamps to 9 (Capitaine)
assert.strictEqual(stepGrid(9, 0, 1), 9) // down from 9 -> clamps to 9
assert.strictEqual(stepGrid(9, 1, 0), 9) // right from 9 -> clamps to 9
assert.strictEqual(stepGrid(9, -1, 0), 8) // left from 9 -> 8 (Nordzy)
assert.strictEqual(stepGrid(8, 0, -1), 5) // up from 8 -> 5 (Phinger)
assert.strictEqual(stepGrid(9, 0, -1), 6) // up from 9 -> 6 (Oreo)

// State parsing and persistence
const bananaTheme = filtered[0]
const stateText = Model.stateDocument(bananaTheme, 128)
const parsed = Model.parseState(stateText)
assert.strictEqual(parsed.ok, true)
assert.strictEqual(parsed.theme.displayName, "Banana")
assert.strictEqual(parsed.size, 128)
assert.strictEqual(Model.parseState("{oops").reason, "corrupt")
assert.strictEqual(Model.parseState("{oops").size, 16)
assert.strictEqual(Model.parseState("").reason, "missing")
assert.strictEqual(Model.parseState("").size, 16)

console.log("model tests: ok")
