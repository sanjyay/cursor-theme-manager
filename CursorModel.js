.pragma library

var SupportedSizes = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]
var DefaultSize = 16

var VisibleThemes = [
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

function safeString(value) {
  return value === undefined || value === null ? "" : String(value)
}

function validSize(value, fallback) {
  var n = Number(value)
  if (SupportedSizes.indexOf(n) !== -1) return n
  return fallback !== undefined ? fallback : DefaultSize
}

function nextSize(currentSize) {
  var current = validSize(currentSize)
  var idx = SupportedSizes.indexOf(current)
  if (idx === -1) return SupportedSizes[0]
  if (idx < SupportedSizes.length - 1) return SupportedSizes[idx + 1]
  return SupportedSizes[idx]
}

function prevSize(currentSize) {
  var current = validSize(currentSize)
  var idx = SupportedSizes.indexOf(current)
  if (idx === -1) return SupportedSizes[0]
  if (idx > 0) return SupportedSizes[idx - 1]
  return SupportedSizes[0]
}

function canIncreaseSize(currentSize) {
  var current = validSize(currentSize)
  var idx = SupportedSizes.indexOf(current)
  return idx !== -1 && idx < SupportedSizes.length - 1
}

function canDecreaseSize(currentSize) {
  var current = validSize(currentSize)
  var idx = SupportedSizes.indexOf(current)
  return idx !== -1 && idx > 0
}

function isInternalTheme(name, path) {
  var s = (safeString(name) + " " + safeString(path)).toLowerCase()
  return s.indexOf("cursorswitcher-themed-") !== -1 ||
         s.indexOf("cursorswitcher-xcursor-") !== -1 ||
         s.indexOf("cursorswitcher-preview-") !== -1 ||
         s.indexOf(".omarchy-cursor-switcher-themed") !== -1
}

function visibleThemeIndex(theme) {
  if (!theme) return -1
  if (isInternalTheme(theme.id, theme.path) || isInternalTheme(theme.displayName, theme.hyprcursor) || isInternalTheme(theme.xcursor, "")) {
    return -1
  }
  if (theme.imported === true || theme.sourceType === "imported") return 9999
  var hypr = safeString(theme.hyprcursor).toLowerCase()
  var xcur = safeString(theme.xcursor).toLowerCase()
  var name = safeString(theme.displayName).toLowerCase()
  for (var i = 0; i < VisibleThemes.length; i++) {
    var target = VisibleThemes[i].toLowerCase()
    if (hypr === target || xcur === target || name === target) return i
    if (target === "nordzy" && (hypr === "nordzy-cursors" || xcur === "nordzy-cursors" || name === "nordzy-cursors")) return i
    if (target === "capitaine" && (hypr === "capitaine-cursors" || xcur === "capitaine-cursors" || name === "capitaine-cursors")) return i
    if (target === "phinger" && (hypr === "phinger-cursors-dark" || xcur === "phinger-cursors-dark")) return i
    if (target === "oreo" && (hypr === "oreo_black_cursors" || xcur === "oreo_black_cursors")) return i
    if (target === "volantes" && (hypr === "volantes_cursors" || xcur === "volantes_cursors")) return i
  }
  return -1
}

function isThemeVisible(theme) {
  if (!theme) return false
  if (isInternalTheme(theme.id, theme.path) || isInternalTheme(theme.displayName, theme.hyprcursor) || isInternalTheme(theme.xcursor, "")) {
    return false
  }
  if (theme.imported === true || theme.sourceType === "imported") return true
  return visibleThemeIndex(theme) !== -1
}

function normalizedTheme(raw) {
  if (!raw || typeof raw !== "object") return null
  var formats = Array.isArray(raw.formats) ? raw.formats.filter(function(value) {
    return value === "hyprcursor" || value === "xcursor"
  }) : []
  var hypr = safeString(raw.hyprcursor)
  var xcursor = safeString(raw.xcursor)
  if (hypr && formats.indexOf("hyprcursor") === -1) formats.push("hyprcursor")
  if (xcursor && formats.indexOf("xcursor") === -1) formats.push("xcursor")
  if (formats.length === 0) return null

  var isImported = raw.imported === true || raw.sourceType === "imported" || String(raw.path || "").indexOf("CursorSwitcher-Imported-") !== -1
  var subtitle = safeString(raw.subtitle)
  if (!subtitle && isImported) subtitle = "Imported"

  var id = safeString(raw.id) || hypr || xcursor
  var displayName = safeString(raw.displayName) || hypr || xcursor
  var nameLower = (displayName || id || hypr).toLowerCase()
  if (nameLower === "banana-green") return null

  return {
    id: id,
    displayName: displayName,
    family: safeString(raw.family) || displayName || id,
    subtitle: subtitle,
    hyprcursor: hypr,
    xcursor: xcursor,
    path: safeString(raw.path),
    formats: formats,
    previewPath: safeString(raw.previewPath),
    bundled: raw.bundled === true,
    imported: isImported,
    sourceType: isImported ? "imported" : (raw.bundled ? "bundled" : "system"),
    contentHash: safeString(raw.contentHash),
    importedAt: safeString(raw.importedAt),
    license: safeString(raw.license),
    previewable: true
  }
}

function canonicalFamily(name) {
  var s = safeString(name).toLowerCase().trim()
  if (s === "nordzy" || s === "nordzy-cursors") return "nordzy"
  if (s === "capitaine" || s === "capitaine-cursors") return "capitaine"
  if (s === "phinger" || s === "phinger-cursors-dark") return "phinger"
  if (s === "oreo" || s === "oreo_black_cursors") return "oreo"
  if (s === "volantes" || s === "volantes_cursors") return "volantes"
  if (s === "banana" || s === "omarchy-banana") return "banana"
  return s
}

function themeKey(theme) {
  if (!theme) return ""
  var family = safeString(theme.family || theme.displayName || theme.id)
  var canon = canonicalFamily(family)
  if (canon) return canon
  return (safeString(theme.id) || safeString(theme.hyprcursor) || safeString(theme.xcursor) || safeString(theme.displayName)).toLowerCase()
}

function mergeTheme(a, b) {
  var preferred = b.bundled || (!a.bundled && b.path.indexOf("/.local/share/icons/") !== -1) || b.imported ? b : a
  var other = preferred === a ? b : a
  var formats = preferred.formats.slice()
  other.formats.forEach(function(format) { if (formats.indexOf(format) === -1) formats.push(format) })
  return {
    id: preferred.id || other.id,
    displayName: preferred.displayName || other.displayName,
    family: preferred.family || other.family || preferred.displayName,
    subtitle: preferred.subtitle || other.subtitle,
    hyprcursor: preferred.hyprcursor || other.hyprcursor,
    xcursor: preferred.xcursor || other.xcursor,
    path: preferred.path || other.path,
    formats: formats,
    previewPath: preferred.previewPath || other.previewPath,
    bundled: preferred.bundled || other.bundled,
    imported: preferred.imported || other.imported,
    sourceType: preferred.sourceType || other.sourceType,
    contentHash: preferred.contentHash || other.contentHash,
    importedAt: preferred.importedAt || other.importedAt,
    license: preferred.license || other.license,
    previewable: true
  }
}

function normalizeThemes(rawThemes) {
  var byKey = {}
  var order = []
  ;(Array.isArray(rawThemes) ? rawThemes : []).forEach(function(raw) {
    var theme = normalizedTheme(raw)
    if (!theme) return
    var key = themeKey(theme)
    if (!key) return
    if (byKey[key]) byKey[key] = mergeTheme(byKey[key], theme)
    else { byKey[key] = theme; order.push(key) }
  })
  var themes = order.map(function(key) { return byKey[key] })
  var filtered = themes.filter(function(theme) {
    return isThemeVisible(theme)
  })
  filtered.sort(function(a, b) {
    var idxA = visibleThemeIndex(a)
    var idxB = visibleThemeIndex(b)
    if (idxA !== idxB) return idxA - idxB
    return safeString(a.displayName).localeCompare(safeString(b.displayName))
  })
  return filtered
}

function parseState(text) {
  var fallback = {
    ok: false,
    reason: "missing",
    theme: null,
    size: DefaultSize,
    importedThemes: []
  }
  if (!safeString(text).trim()) return fallback
  try {
    var raw = JSON.parse(text)
    if (!raw || typeof raw !== "object") return { ok: false, reason: "invalid", theme: null, size: DefaultSize, importedThemes: [] }

    var theme = raw.theme ? normalizedTheme(raw.theme) : (raw.manualTheme ? normalizedTheme(raw.manualTheme) : null)
    var size = validSize(raw.size !== undefined ? raw.size : raw.manualSize, DefaultSize)
    var importedThemes = Array.isArray(raw.importedThemes) ? raw.importedThemes : []

    return {
      ok: true,
      reason: "",
      theme: theme,
      size: size,
      importedThemes: importedThemes
    }
  } catch (error) {
    return { ok: false, reason: "corrupt", theme: null, size: DefaultSize, importedThemes: [] }
  }
}

function stateDocument(arg1, arg2, arg3) {
  var doc = { version: 2 }
  if (typeof arg1 === "object" && arg1 !== null && !arg1.displayName && !arg1.hyprcursor && !arg1.xcursor) {
    var s = arg1
    doc.theme = s.theme ? {
      displayName: s.theme.displayName,
      hyprcursor: s.theme.hyprcursor,
      xcursor: s.theme.xcursor
    } : (s.manualTheme ? {
      displayName: s.manualTheme.displayName,
      hyprcursor: s.manualTheme.hyprcursor,
      xcursor: s.manualTheme.xcursor
    } : null)
    doc.size = validSize(s.size !== undefined ? s.size : s.manualSize, DefaultSize)
    doc.importedThemes = s.importedThemes || []
  } else {
    var theme = arg1
    var size = validSize(arg2, DefaultSize)
    var importedThemes = Array.isArray(arg3) ? arg3 : []
    doc.theme = theme ? {
      displayName: theme.displayName,
      hyprcursor: theme.hyprcursor,
      xcursor: theme.xcursor
    } : null
    doc.size = size
    doc.importedThemes = importedThemes
  }
  return JSON.stringify(doc, null, 2) + "\n"
}

function findTheme(themes, wanted) {
  if (!wanted || !Array.isArray(themes)) return null
  var isStr = typeof wanted === "string"
  var wantedName = (isStr ? wanted : safeString(wanted.displayName)).toLowerCase()
  var wantedHypr = (isStr ? wanted : safeString(wanted.hyprcursor)).toLowerCase()
  var wantedX = (isStr ? wanted : safeString(wanted.xcursor)).toLowerCase()
  var wantedId = (isStr ? wanted : safeString(wanted.id)).toLowerCase()
  for (var i = 0; i < themes.length; i++) {
    var theme = themes[i]
    if (wantedName && theme.displayName.toLowerCase() === wantedName) return theme
    if (wantedHypr && theme.hyprcursor.toLowerCase() === wantedHypr) return theme
    if (wantedX && theme.xcursor.toLowerCase() === wantedX) return theme
    if (wantedId && theme.id && theme.id.toLowerCase() === wantedId) return theme
  }
  return null
}

function fallbackTheme(themes, currentXcursor) {
  var current = safeString(currentXcursor).toLowerCase()
  if (current) {
    for (var i = 0; i < themes.length; i++) {
      if (themes[i].xcursor.toLowerCase() === current ||
          themes[i].hyprcursor.toLowerCase() === current ||
          themes[i].displayName.toLowerCase() === current) {
        return themes[i]
      }
    }
  }
  for (var k = 0; k < themes.length; k++) {
    if (themes[k].displayName.toLowerCase() === "banana" ||
        themes[k].hyprcursor.toLowerCase() === "banana" ||
        themes[k].xcursor.toLowerCase() === "banana") {
      return themes[k]
    }
  }
  return themes.length ? themes[0] : null
}

function themeEquals(a, b) {
  if (!a || !b) return false
  return (safeString(a.id) === safeString(b.id) && safeString(a.id) !== "") ||
         (safeString(a.displayName) === safeString(b.displayName) && safeString(a.displayName) !== "") ||
         (safeString(a.hyprcursor) === safeString(b.hyprcursor) && safeString(a.hyprcursor) !== "") ||
         (safeString(a.xcursor) === safeString(b.xcursor) && safeString(a.xcursor) !== "")
}

function applyArguments(scriptPath, theme, size, preview) {
  if (!theme) return []
  var args = [scriptPath, "apply",
    "--hyprcursor", theme.hyprcursor || "-",
    "--xcursor", theme.xcursor || "-"]
  if (theme.path) {
    args.push("--theme-path", theme.path)
  }
  args.push("--size", String(validSize(size)),
    preview ? "--preview" : "--commit")
  return args
}

function initialPreviewState(theme, size) {
  return { committedTheme: theme, committedSize: validSize(size), previewTheme: null, previewSize: 0 }
}

function startPreview(state, theme, size) {
  return {
    committedTheme: state.committedTheme,
    committedSize: state.committedSize,
    previewTheme: theme,
    previewSize: validSize(size)
  }
}

function cancelPreview(state) {
  return {
    committedTheme: state.committedTheme,
    committedSize: state.committedSize,
    previewTheme: null,
    previewSize: 0
  }
}

function commitPreview(state, theme, size) {
  return initialPreviewState(theme, size)
}

function previewColumns(containerWidth, cardWidth, columnSpacing, paddingHorizontal, totalCount) {
  var pad = paddingHorizontal !== undefined ? paddingHorizontal : 16
  var cw = cardWidth !== undefined ? cardWidth : 72
  var cs = columnSpacing !== undefined ? columnSpacing : 14
  var count = Math.max(1, Number(totalCount) || 6)
  var avail = (Number(containerWidth) || 0) - pad * 2

  if (count <= 3) {
    var wCount = count * cw + (count - 1) * cs
    if (avail >= wCount) return count
    if (count === 3 && avail >= (2 * cw + cs)) return 2
    return 1
  }

  if (count === 4) {
    var w4 = 4 * cw + 3 * cs
    if (avail >= w4) return 4
    if (avail >= (2 * cw + cs)) return 2
    return 1
  }

  if (count === 5) {
    var w5 = 5 * cw + 4 * cs
    if (avail >= w5) return 5
    if (avail >= (3 * cw + 2 * cs)) return 3
    if (avail >= (2 * cw + cs)) return 2
    return 1
  }

  // 6 or more roles
  var w6 = 6 * cw + 5 * cs
  var w3 = 3 * cw + 2 * cs
  var w2 = 2 * cw + 1 * cs

  if (avail >= w6) return 6
  if (avail >= w3) return 3
  if (avail >= w2) return 2
  return 1
}

function previewRows(totalCount, columns) {
  var count = Math.max(0, Number(totalCount) || 0)
  var cols = Math.max(1, Number(columns) || 1)
  return Math.ceil(count / cols)
}

function previewGridGeometry(totalCount, containerWidth, cardWidth, itemHeight, columnSpacing, rowSpacing, paddingHorizontal, paddingVertical) {
  var count = Math.max(0, Number(totalCount) || 0)
  var width = Math.max(0, Number(containerWidth) || 0)
  var cw = cardWidth !== undefined ? cardWidth : 72
  var ih = itemHeight !== undefined ? itemHeight : 92
  var cs = columnSpacing !== undefined ? columnSpacing : 14
  var rs = rowSpacing !== undefined ? rowSpacing : 12
  var padH = paddingHorizontal !== undefined ? paddingHorizontal : 16
  var padV = paddingVertical !== undefined ? paddingVertical : 14

  var cols = previewColumns(width, cw, cs, padH, count)
  var rows = previewRows(count, cols)

  var gridWidth = cols * cw + Math.max(0, cols - 1) * cs
  var gridHeight = rows * ih + Math.max(0, rows - 1) * rs
  var gridX = (width - gridWidth) / 2
  var gridY = padV

  var cards = []
  var fitsInside = true

  for (var i = 0; i < count; i++) {
    var col = i % cols
    var row = Math.floor(i / cols)
    var cx = gridX + col * (cw + cs)
    var cy = gridY + row * (ih + rs)
    var inBounds = cx >= 0 && (cx + cw) <= width
    if (!inBounds) fitsInside = false
    cards.push({ index: i, col: col, row: row, x: cx, y: cy, inBounds: inBounds })
  }

  return {
    columns: cols,
    rows: rows,
    gridWidth: gridWidth,
    gridHeight: gridHeight,
    gridX: gridX,
    gridY: gridY,
    containerHeight: gridHeight + padV * 2,
    fitsInside: fitsInside,
    cards: cards
  }
}

if (typeof module !== "undefined") module.exports = {
  SupportedSizes: SupportedSizes,
  DefaultSize: DefaultSize,
  VisibleThemes: VisibleThemes,
  isInternalTheme: isInternalTheme,
  isThemeVisible: isThemeVisible,
  visibleThemeIndex: visibleThemeIndex,
  validSize: validSize,
  nextSize: nextSize,
  prevSize: prevSize,
  canIncreaseSize: canIncreaseSize,
  canDecreaseSize: canDecreaseSize,
  normalizedTheme: normalizedTheme,
  normalizeThemes: normalizeThemes,
  parseState: parseState,
  stateDocument: stateDocument,
  findTheme: findTheme,
  fallbackTheme: fallbackTheme,
  themeEquals: themeEquals,
  applyArguments: applyArguments,
  initialPreviewState: initialPreviewState,
  startPreview: startPreview,
  cancelPreview: cancelPreview,
  commitPreview: commitPreview,
  previewColumns: previewColumns,
  previewRows: previewRows,
  previewGridGeometry: previewGridGeometry
}

