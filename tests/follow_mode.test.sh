#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

echo "Running follow_mode tests..."

# Run mappings unit test
node "$SCRIPT_DIR/mappings.test.js"

# Test state migration and follow mode preservation in Model
ROOT_DIR="$ROOT" node - <<'NODE'
const assert = require("assert")
const fs = require("fs")
const vm = require("vm")
const path = require("path")

const rootDir = process.env.ROOT_DIR || "."

function loadModule(relPath) {
  const file = path.join(rootDir, relPath)
  const source = fs.readFileSync(file, "utf8").replace(/^\.pragma library\s*/, "")
  const sandbox = { module: { exports: {} }, console }
  vm.runInNewContext(source, sandbox, { filename: relPath })
  return sandbox.module.exports
}

const Model = loadModule("CursorModel.js")
const Mappings = loadModule("ThemeCursorMappings.js")

// 1. Default mode migration from v1 state
const v1State = JSON.stringify({ version: 1, theme: { displayName: "Banana", hyprcursor: "Banana", xcursor: "Banana" }, size: 32 })
const parsedV1 = Model.parseState(v1State)
assert.strictEqual(parsedV1.ok, true)
assert.strictEqual(parsedV1.mode, "manual")
assert.strictEqual(parsedV1.manualTheme.displayName, "Banana")
assert.strictEqual(parsedV1.manualSize, 32)
assert.strictEqual(parsedV1.followSize, 32)

// 2. Manual selection preserved when enabling Follow mode
const v2Follow = Model.stateDocument(
  "follow-omarchy",
  { displayName: "Phinger", hyprcursor: "Phinger", xcursor: "Phinger" }, // manualTheme
  48, // manualSize
  24, // followSize
  { "tokyo-night": "Nordzy" }, // mappings
  [],
  { displayName: "Nordzy", hyprcursor: "Nordzy", xcursor: "Nordzy" } // active
)
const parsedV2 = Model.parseState(v2Follow)
assert.strictEqual(parsedV2.mode, "follow-omarchy")
assert.strictEqual(parsedV2.manualTheme.displayName, "Phinger")
assert.strictEqual(parsedV2.manualSize, 48)
assert.strictEqual(parsedV2.followSize, 24)
assert.strictEqual(parsedV2.size, 24)

// 3. Switching back to Manual restores manualTheme and manualSize
const v2Manual = Model.stateDocument(
  "manual",
  parsedV2.manualTheme,
  parsedV2.manualSize,
  parsedV2.followSize,
  parsedV2.follow.mappings,
  parsedV2.importedThemes,
  parsedV2.manualTheme
)
const parsedBack = Model.parseState(v2Manual)
assert.strictEqual(parsedBack.mode, "manual")
assert.strictEqual(parsedBack.theme.displayName, "Phinger")
assert.strictEqual(parsedBack.size, 48)

// 4. Test mapping resolution for diverse Omarchy theme names
const available = [
  { displayName: "Adwaita", hyprcursor: "Adwaita", xcursor: "Adwaita" },
  { displayName: "Banana", hyprcursor: "Banana", xcursor: "Banana" },
  { displayName: "Bibata-Catppuccin-Mocha", hyprcursor: "Bibata-Catppuccin-Mocha", xcursor: "Bibata-Catppuccin-Mocha" },
  { displayName: "Nordzy", hyprcursor: "Nordzy", xcursor: "Nordzy" },
  { displayName: "Tokyonight-Dark", hyprcursor: "Tokyonight-Dark", xcursor: "Tokyonight-Dark" },
  { id: "CursorSwitcher-Imported-My-Imported-1234", displayName: "My-Imported-Cursor", sourceType: "imported" }
]

// Catppuccin -> Bibata-Catppuccin-Mocha
let r = Mappings.resolveMappedTheme("Catppuccin Mocha", {}, available)
assert.strictEqual(r.theme.displayName, "Bibata-Catppuccin-Mocha")

// Tokyo Night -> Nordzy (or mapped default)
r = Mappings.resolveMappedTheme("Tokyo Night", {}, available)
assert.strictEqual(r.theme.displayName, "Nordzy")

// Unmapped -> Adwaita fallback
r = Mappings.resolveMappedTheme("some-custom-omarchy-theme", {}, available)
assert.strictEqual(r.theme.displayName, "Adwaita")

// User mapped to imported cursor
const userMap = { "some-custom-omarchy-theme": "My-Imported-Cursor" }
r = Mappings.resolveMappedTheme("some-custom-omarchy-theme", userMap, available)
assert.strictEqual(r.theme.displayName, "My-Imported-Cursor")
assert.strictEqual(r.source, "user")

NODE

echo "follow_mode tests: ok"
