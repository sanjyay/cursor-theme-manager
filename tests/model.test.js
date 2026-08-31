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
  { displayName: "Banana-Dracula", hyprcursor: "", xcursor: "Banana-Dracula", formats: ["xcursor"] },
  { displayName: "Yaru", hyprcursor: "", xcursor: "Yaru", formats: ["xcursor"] },
  { displayName: "OtherUnknown", hyprcursor: "", xcursor: "OtherUnknown", formats: ["xcursor"] }
]

const filtered = Model.normalizeThemes(mockDiscovered)
// 1. Exactly 9 themes are exposed
assert.strictEqual(filtered.length, 9)
// 2. Ordering is exact
assert.deepStrictEqual(Array.from(filtered.map(t => t.displayName)), expectedVisible)
// 3. Unlisted themes (including Banana-Green) are filtered out
assert.strictEqual(filtered.some(t => t.displayName === "Banana-Green"), false)
assert.strictEqual(filtered.some(t => t.displayName === "Banana-Dracula"), false)
assert.strictEqual(filtered.some(t => t.displayName === "Banana-Blue"), false)
assert.strictEqual(filtered.some(t => t.displayName === "Yaru"), false)
assert.strictEqual(filtered.some(t => t.displayName === "OtherUnknown"), false)

// 4. Fallback handling for persisted hidden/unlisted theme
assert.strictEqual(Model.findTheme(filtered, { displayName: "Banana-Dracula", xcursor: "Banana-Dracula" }), null)
assert.strictEqual(Model.fallbackTheme(filtered, "Banana-Dracula").displayName, "Banana")
assert.strictEqual(Model.fallbackTheme(filtered, "Banana-Catppuccin-Mocha").displayName, "Banana-Catppuccin-Mocha")
assert.strictEqual(Model.fallbackTheme(filtered, "Nordzy").displayName, "Nordzy")

// 5. Internal generated theme exclusion
const mockWithInternal = mockDiscovered.concat([
  { displayName: "CursorSwitcher-Themed-Banana-08ede60d3562", hyprcursor: "CursorSwitcher-Themed-Banana-08ede60d3562", xcursor: "CursorSwitcher-Themed-Banana-08ede60d3562", formats: ["hyprcursor", "xcursor"], path: "/home/user/.local/share/icons/CursorSwitcher-Themed-Banana-08ede60d3562" },
  { displayName: "CursorSwitcher-XCursor-Adwaita-2a4b6c8d", hyprcursor: "CursorSwitcher-XCursor-Adwaita-2a4b6c8d", xcursor: "Adwaita", formats: ["hyprcursor"], path: "/home/user/.local/share/icons/CursorSwitcher-XCursor-Adwaita-2a4b6c8d" },
  { displayName: "CursorSwitcher-Preview-Banana", hyprcursor: "CursorSwitcher-Preview-Banana", xcursor: "Banana", formats: ["hyprcursor"] }
])
const normalizedClean = Model.normalizeThemes(mockWithInternal)
assert.strictEqual(normalizedClean.some(t => t.displayName.startsWith("CursorSwitcher-Themed-")), false)
assert.strictEqual(normalizedClean.some(t => t.displayName.startsWith("CursorSwitcher-XCursor-")), false)
assert.strictEqual(normalizedClean.some(t => t.displayName.startsWith("CursorSwitcher-Preview-")), false)
assert.strictEqual(normalizedClean.length, 9)

// 6. Vertical List navigation (Up/Down, Home/End)
function stepList(currentIndex, delta, maxCount) {
  return Math.max(0, Math.min(maxCount - 1, currentIndex + delta))
}
assert.strictEqual(stepList(0, 1, 9), 1) // Down from 0 -> 1
assert.strictEqual(stepList(1, 1, 9), 2) // Down from 1 -> 2
assert.strictEqual(stepList(8, 1, 9), 8) // Clamps at bottom
assert.strictEqual(stepList(8, -1, 9), 7) // Up from 8 -> 7
assert.strictEqual(stepList(0, -1, 9), 0) // Clamps at top

// State parsing and persistence (v1 & v2 compatibility)
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

// Schema v2 stateDocument with importedThemes
const phingerTheme = filtered.find(t => t.displayName === "Phinger")
const v2Doc = Model.stateDocument(
  phingerTheme,
  32,
  [{ id: "Custom-Imported", displayName: "Custom (Imported)", sourceType: "imported", formats: ["xcursor"] }]
)

const parsedV2 = Model.parseState(v2Doc)
assert.strictEqual(parsedV2.ok, true)
assert.strictEqual(parsedV2.theme.displayName, "Phinger")
assert.strictEqual(parsedV2.size, 32)
assert.strictEqual(parsedV2.importedThemes.length, 1)

// Imported themes visibility and ordering test
const rawWithImported = mockDiscovered.concat([
  { id: "MyCustom", displayName: "My Custom Cursor", sourceType: "imported", formats: ["xcursor"], path: "/tmp/custom" }
])
const normalizedWithImported = Model.normalizeThemes(rawWithImported)
assert.strictEqual(normalizedWithImported.some(t => t.displayName === "My Custom Cursor"), true)
const customTheme = normalizedWithImported.find(t => t.displayName === "My Custom Cursor")
assert.strictEqual(customTheme.imported, true)
assert.strictEqual(customTheme.sourceType, "imported")
// Responsive preview layout calculation tests
// 1. Column selection based on available width
assert.strictEqual(Model.previewColumns(600, 72, 14, 16), 6) // Wide window -> 6 cols
assert.strictEqual(Model.previewColumns(550, 72, 14, 16), 6) // >= 534px -> 6 cols
assert.strictEqual(Model.previewColumns(533, 72, 14, 16), 3) // < 534px -> 3 cols (tiled 50/50)
assert.strictEqual(Model.previewColumns(442, 72, 14, 16), 3) // 800px window preview pane -> 3 cols
assert.strictEqual(Model.previewColumns(380, 72, 14, 16), 3) // Narrow tiled preview pane -> 3 cols
assert.strictEqual(Model.previewColumns(270, 72, 14, 16), 2) // < 276px -> 2 cols
assert.strictEqual(Model.previewColumns(180, 72, 14, 16), 1) // Very narrow -> 1 col

// 2. Row count based on items and columns
assert.strictEqual(Model.previewRows(6, 6), 1) // 6x1 single row
assert.strictEqual(Model.previewRows(6, 3), 2) // 3x2 two rows (balanced)
assert.strictEqual(Model.previewRows(6, 2), 3) // 2x3 three rows
assert.strictEqual(Model.previewRows(6, 1), 6) // 1x6 vertical

// 3. Exact grid geometry and boundary containment for 50/50 tiled window (442px container)
const tiledGeom = Model.previewGridGeometry(6, 442, 72, 92, 14, 12, 16, 14)
assert.strictEqual(tiledGeom.columns, 3)
assert.strictEqual(tiledGeom.rows, 2)
assert.strictEqual(tiledGeom.fitsInside, true)
assert.strictEqual(tiledGeom.gridWidth, 3 * 72 + 2 * 14) // 244px
assert.strictEqual(tiledGeom.gridHeight, 2 * 92 + 1 * 12) // 196px
assert.strictEqual(tiledGeom.containerHeight, 196 + 28) // 224px (expanded from 120px)

// Check every card in the 50/50 tiled window:
assert.strictEqual(tiledGeom.cards.length, 6)
for (const card of tiledGeom.cards) {
  assert.strictEqual(card.inBounds, true)
  assert.ok(card.x >= 0, `Card ${card.index} left (${card.x}) must be >= 0`)
  assert.ok(card.x + 72 <= 442, `Card ${card.index} right (${card.x + 72}) must be <= 442`)
}

// Row 1 (Default, Pointer, Text) and Row 2 (Move, Resize, Wait)
assert.strictEqual(tiledGeom.cards[0].row, 0)
assert.strictEqual(tiledGeom.cards[1].row, 0)
assert.strictEqual(tiledGeom.cards[2].row, 0)
assert.strictEqual(tiledGeom.cards[3].row, 1)
assert.strictEqual(tiledGeom.cards[4].row, 1)
assert.strictEqual(tiledGeom.cards[5].row, 1)
assert.ok(tiledGeom.cards[3].y > tiledGeom.cards[0].y, "Row 2 must be positioned below Row 1")

// 4. Exact grid geometry for wide full-screen window (600px container)
const wideGeom = Model.previewGridGeometry(6, 600, 72, 92, 14, 12, 16, 14)
assert.strictEqual(wideGeom.columns, 6)
assert.strictEqual(wideGeom.rows, 1)
assert.strictEqual(wideGeom.fitsInside, true)
assert.strictEqual(wideGeom.gridWidth, 6 * 72 + 5 * 14) // 502px
assert.strictEqual(wideGeom.gridHeight, 92) // 92px
assert.strictEqual(wideGeom.containerHeight, 92 + 28) // 120px
for (const card of wideGeom.cards) {
  assert.strictEqual(card.inBounds, true)
  assert.strictEqual(card.row, 0) // all single row
  assert.ok(card.x >= 0)
  assert.ok(card.x + 72 <= 600)
}

// 5. Old implementation failure reproduction check:
// Old implementation placed a fixed 502px row centered in a 442px container
const oldRowX = (442 - 502) / 2 // -30px
const oldRowRight = oldRowX + 502 // 472px
assert.strictEqual(oldRowX, -30) // Overflow left by 30px
assert.strictEqual(oldRowRight, 472) // Overflow right by 30px (472 > 442)
// New implementation eliminates both overflows completely:
assert.ok(tiledGeom.gridX >= 16) // grid starts at >= 16px padding
assert.ok(tiledGeom.gridX + tiledGeom.gridWidth <= 442 - 16) // grid ends at <= 426px

console.log("model tests: ok")

