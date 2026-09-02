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

const mockDiscovered = [
  { id: "Adwaita", displayName: "Adwaita", hyprcursor: "", xcursor: "Adwaita", formats: ["xcursor"], sourceType: "system" },
  { id: "CustomUser", displayName: "CustomUser", hyprcursor: "", xcursor: "CustomUser", formats: ["xcursor"], sourceType: "user" },
  { id: "ImportedBibata", displayName: "Bibata Modern", hyprcursor: "Bibata", xcursor: "Bibata", formats: ["hyprcursor", "xcursor"], sourceType: "imported", imported: true }
]

const filtered = Model.normalizeThemes(mockDiscovered)
assert.strictEqual(filtered.length, 3)
// Imported is first, then User, then System
assert.strictEqual(filtered[0].displayName, "Bibata Modern")
assert.strictEqual(filtered[0].sourceType, "imported")
assert.strictEqual(filtered[1].displayName, "CustomUser")
assert.strictEqual(filtered[1].sourceType, "user")
assert.strictEqual(filtered[2].displayName, "Adwaita")
assert.strictEqual(filtered[2].sourceType, "system")

// Internal generated theme exclusion vs imported theme preservation
const mockWithInternal = mockDiscovered.concat([
  { id: "CursorSwitcher-Imported-Banana-9134e802e21a", displayName: "Banana", hyprcursor: "CursorSwitcher-XCursor-CursorSwitcher-Imported-Banana-9134e802e21a-f50e2d2168bc", xcursor: "CursorSwitcher-Imported-Banana-9134e802e21a", formats: ["xcursor", "hyprcursor"], path: "/home/user/.local/share/icons/CursorSwitcher-Imported-Banana-9134e802e21a", sourceType: "imported", imported: true },
  { id: "CursorSwitcher-Themed-Banana-08ede60d3562", displayName: "CursorSwitcher-Themed-Banana", hyprcursor: "CursorSwitcher-Themed-Banana-08ede60d3562", xcursor: "CursorSwitcher-Themed-Banana-08ede60d3562", formats: ["hyprcursor", "xcursor"], path: "/home/user/.local/share/icons/CursorSwitcher-Themed-Banana-08ede60d3562" },
  { id: "CursorSwitcher-XCursor-Adwaita-2a4b6c8d", displayName: "CursorSwitcher-XCursor-Adwaita", hyprcursor: "CursorSwitcher-XCursor-Adwaita-2a4b6c8d", xcursor: "Adwaita", formats: ["hyprcursor"], path: "/home/user/.local/share/icons/CursorSwitcher-XCursor-Adwaita-2a4b6c8d" },
  { id: "CursorSwitcher-Preview-Banana", displayName: "CursorSwitcher-Preview-Banana", hyprcursor: "CursorSwitcher-Preview-Banana", xcursor: "Banana", formats: ["hyprcursor"] },
  { id: "Banana-Hyprcursor", displayName: "Extracted Theme", hyprcursor: "Extracted Theme", xcursor: "", formats: ["hyprcursor"], path: "/home/user/.local/share/icons/Banana-Hyprcursor" }
])
const normalizedClean = Model.normalizeThemes(mockWithInternal)
assert.strictEqual(normalizedClean.some(t => t.id.startsWith("CursorSwitcher-Themed-")), false)
assert.strictEqual(normalizedClean.some(t => t.id.startsWith("CursorSwitcher-XCursor-")), false)
assert.strictEqual(normalizedClean.some(t => t.id.startsWith("CursorSwitcher-Preview-")), false)
assert.strictEqual(normalizedClean.some(t => t.displayName === "Extracted Theme"), false)
// The imported theme Banana MUST be present!
assert.strictEqual(normalizedClean.some(t => t.displayName === "Banana" && t.imported === true), true)
assert.strictEqual(normalizedClean.length, 4)

// Fallback handling
assert.strictEqual(Model.findTheme(filtered, "Adwaita").displayName, "Adwaita")
assert.strictEqual(Model.fallbackTheme(filtered, "Adwaita").displayName, "Adwaita")
assert.strictEqual(Model.fallbackTheme(filtered, "NonExistent").displayName, "Bibata Modern")
assert.strictEqual(Model.fallbackTheme([], "NonExistent"), null)

// State parsing and persistence
const adwaitaTheme = filtered[2]
const stateText = Model.stateDocument(adwaitaTheme, 128)
const parsed = Model.parseState(stateText)
assert.strictEqual(parsed.ok, true)
assert.strictEqual(parsed.theme.displayName, "Adwaita")
assert.strictEqual(parsed.size, 128)
assert.strictEqual(Model.parseState("{oops").reason, "corrupt")
assert.strictEqual(Model.parseState("{oops").size, 16)
assert.strictEqual(Model.parseState("").reason, "missing")
assert.strictEqual(Model.parseState("").size, 16)

// Responsive preview layout calculation tests
assert.strictEqual(Model.previewColumns(600, 72, 14, 16), 6) // Wide window -> 6 cols
assert.strictEqual(Model.previewColumns(550, 72, 14, 16), 6) // >= 534px -> 6 cols
assert.strictEqual(Model.previewColumns(533, 72, 14, 16), 3) // < 534px -> 3 cols (tiled 50/50)
assert.strictEqual(Model.previewColumns(442, 72, 14, 16), 3) // 800px window preview pane -> 3 cols
assert.strictEqual(Model.previewColumns(380, 72, 14, 16), 3) // Narrow tiled preview pane -> 3 cols
assert.strictEqual(Model.previewColumns(270, 72, 14, 16), 2) // < 276px -> 2 cols
assert.strictEqual(Model.previewColumns(180, 72, 14, 16), 1) // Very narrow -> 1 col

// Row count based on items and columns
assert.strictEqual(Model.previewRows(6, 6), 1) // 6x1 single row
assert.strictEqual(Model.previewRows(6, 3), 2) // 3x2 two rows (balanced)
assert.strictEqual(Model.previewRows(6, 2), 3) // 2x3 three rows
assert.strictEqual(Model.previewRows(6, 1), 6) // 1x6 vertical

// Grid geometry
const tiledGeom = Model.previewGridGeometry(6, 442, 72, 92, 14, 12, 16, 14)
assert.strictEqual(tiledGeom.columns, 3)
assert.strictEqual(tiledGeom.rows, 2)
assert.strictEqual(tiledGeom.fitsInside, true)
assert.strictEqual(tiledGeom.gridWidth, 3 * 72 + 2 * 14) // 244px
assert.strictEqual(tiledGeom.gridHeight, 2 * 92 + 1 * 12) // 196px
assert.strictEqual(tiledGeom.containerHeight, 196 + 28) // 224px

console.log("model tests: ok")
