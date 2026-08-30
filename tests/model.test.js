const assert = require("assert")
const fs = require("fs")
const vm = require("vm")

const source = fs.readFileSync("CursorModel.js", "utf8").replace(/^\.pragma library\s*/, "")
const sandbox = { module: { exports: {} }, console }
vm.runInNewContext(source, sandbox, { filename: "CursorModel.js" })
const Model = sandbox.module.exports

assert.deepStrictEqual(Array.from(Model.SupportedSizes), [16, 20, 24, 28, 32, 40, 48])
assert.strictEqual(Model.validSize(32), 32)
assert.strictEqual(Model.validSize(33), 24)
assert.strictEqual(Model.validSize("16"), 16)

const both = Model.normalizedTheme({ displayName: "Both", hyprcursor: "Both-H", xcursor: "Both-X", formats: [] })
assert.deepStrictEqual(Array.from(both.formats), ["hyprcursor", "xcursor"])
assert.strictEqual(Model.normalizedTheme({ displayName: "Icons only", formats: [] }), null)

const deduped = Model.normalizeThemes([
  { displayName: "System", hyprcursor: "Test", formats: ["hyprcursor"], path: "/usr/share/icons/Test" },
  { displayName: "User", hyprcursor: "Test", xcursor: "Test", formats: ["hyprcursor", "xcursor"], path: "/home/u/.local/share/icons/Test" },
  { displayName: "Omarchy Banana", hyprcursor: "Omarchy-Banana", xcursor: "Omarchy-Banana", formats: ["hyprcursor", "xcursor"], bundled: true }
])
assert.strictEqual(deduped.length, 2)
assert.strictEqual(deduped[0].displayName, "Omarchy Banana")
assert.strictEqual(deduped[1].displayName, "User")
assert.deepStrictEqual(Array.from(deduped[1].formats), ["hyprcursor", "xcursor"])

const stateText = Model.stateDocument(both, 28)
const parsed = Model.parseState(stateText)
assert.strictEqual(parsed.ok, true)
assert.strictEqual(parsed.theme.hyprcursor, "Both-H")
assert.strictEqual(parsed.size, 28)
assert.strictEqual(Model.parseState("{oops").reason, "corrupt")
assert.strictEqual(Model.parseState("").reason, "missing")
assert.strictEqual(Model.findTheme(deduped, { hyprcursor: "missing", xcursor: "missing" }), null)
assert.strictEqual(Model.fallbackTheme(deduped, "Test").displayName, "User")

assert.deepStrictEqual(Array.from(Model.applyArguments("/helper", both, 32, true)),
  ["/helper", "apply", "--hyprcursor", "Both-H", "--xcursor", "Both-X", "--size", "32", "--preview"])
const xonly = Model.normalizedTheme({ displayName: "X", xcursor: "X", formats: ["xcursor"] })
assert.deepStrictEqual(Array.from(Model.applyArguments("/helper", xonly, 24, false)),
  ["/helper", "apply", "--hyprcursor", "-", "--xcursor", "X", "--size", "24", "--commit"])

let preview = Model.initialPreviewState(both, 24)
preview = Model.startPreview(preview, xonly, 32)
assert.strictEqual(preview.previewTheme.displayName, "X")
assert.strictEqual(preview.committedTheme.displayName, "Both")
preview = Model.cancelPreview(preview)
assert.strictEqual(preview.previewTheme, null)
assert.strictEqual(preview.committedTheme.displayName, "Both")
preview = Model.commitPreview(preview, xonly, 40)
assert.strictEqual(preview.committedTheme.displayName, "X")
assert.strictEqual(preview.committedSize, 40)

console.log("model tests: ok")
