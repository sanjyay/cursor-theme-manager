.pragma library

var SupportedSizes = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]
var DefaultSize = 16

function sanitizeString(value, maxLen) {
  if (value === undefined || value === null) return ""
  var s = String(value)
  var limit = maxLen !== undefined ? maxLen : 256
  // Remove NUL and unprintable control characters, normalize whitespace
  var cleaned = s.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]/g, "").replace(/\s+/g, " ").trim()
  return cleaned.length > limit ? cleaned.substring(0, limit) : cleaned
}

function safeString(value) {
  return sanitizeString(value, 256)
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
  var s = (sanitizeString(name, 512) + " " + sanitizeString(path, 1024)).toLowerCase()
  return s.indexOf("cursorswitcher-themed-") !== -1 ||
         s.indexOf("cursorswitcher-xcursor-") !== -1 ||
         s.indexOf("cursorswitcher-preview-") !== -1 ||
         s.indexOf(".omarchy-cursor-switcher-themed") !== -1 ||
         s.indexOf(".omarchy-cursor-switcher-converted") !== -1
}

function isThemeVisible(theme) {
  if (!theme) return false
  return !isInternalTheme(theme.id, theme.path) &&
         !isInternalTheme(theme.displayName, theme.hyprcursor) &&
         !isInternalTheme(theme.xcursor, "")
}

function normalizedTheme(raw) {
  if (!raw || typeof raw !== "object") return null
  var formats = Array.isArray(raw.formats) ? raw.formats.filter(function(value) {
    return value === "hyprcursor" || value === "xcursor"
  }) : []
  var hypr = sanitizeString(raw.hyprcursor, 256)
  var xcursor = sanitizeString(raw.xcursor, 256)
  if (hypr && formats.indexOf("hyprcursor") === -1) formats.push("hyprcursor")
  if (xcursor && formats.indexOf("xcursor") === -1) formats.push("xcursor")
  if (formats.length === 0) return null

  var isImported = raw.imported === true || raw.sourceType === "imported" || String(raw.path || "").indexOf("CursorSwitcher-Imported-") !== -1
  var sourceType = isImported ? "imported" : (raw.sourceType === "system" ? "system" : "user")
  var subtitle = sanitizeString(raw.subtitle, 1024)
  if (!subtitle) {
    subtitle = isImported ? "Imported" : (sourceType === "system" ? "System" : "User")
  }

  var id = sanitizeString(raw.id, 256) || hypr || xcursor
  var displayName = sanitizeString(raw.displayName, 256) || hypr || xcursor

  return {
    id: id,
    displayName: displayName,
    family: sanitizeString(raw.family, 256) || displayName || id,
    subtitle: subtitle,
    hyprcursor: hypr,
    xcursor: xcursor,
    path: sanitizeString(raw.path, 4096),
    formats: formats,
    previewPath: sanitizeString(raw.previewPath, 4096),
    imported: isImported,
    sourceType: sourceType,
    contentHash: sanitizeString(raw.contentHash, 128),
    importedAt: sanitizeString(raw.importedAt, 128),
    license: sanitizeString(raw.license, 128),
    previewable: true
  }
}

function canonicalFamily(name) {
  return sanitizeString(name, 256).toLowerCase().trim()
}

function themeKey(theme) {
  if (!theme) return ""
  return (sanitizeString(theme.id, 256) || sanitizeString(theme.hyprcursor, 256) || sanitizeString(theme.xcursor, 256) || sanitizeString(theme.displayName, 256)).toLowerCase()
}

function mergeTheme(a, b) {
  var preferred = b.imported || (a.sourceType === "system" && b.sourceType === "user") ? b : a
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
  var list = Array.isArray(rawThemes) ? rawThemes.slice(0, 1024) : []
  list.forEach(function(raw) {
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
    var typeOrderA = a.sourceType === "imported" ? 0 : (a.sourceType === "user" ? 1 : 2)
    var typeOrderB = b.sourceType === "imported" ? 0 : (b.sourceType === "user" ? 1 : 2)
    if (typeOrderA !== typeOrderB) return typeOrderA - typeOrderB
    return sanitizeString(a.displayName, 256).localeCompare(sanitizeString(b.displayName, 256))
  })
  return filtered
}

function parseState(text) {
  var fallback = {
    ok: false,
    reason: "missing",
    theme: null,
    size: DefaultSize,
    importedThemes: [],
    integrationConsent: false,
    integrationInstalled: false
  }
  if (!text || typeof text !== "string" || !text.trim()) return fallback
  if (text.length > 65536) return { ok: false, reason: "corrupt", theme: null, size: DefaultSize, importedThemes: [], integrationConsent: false, integrationInstalled: false }

  try {
    var raw = JSON.parse(text)
    if (!raw || typeof raw !== "object") return { ok: false, reason: "invalid", theme: null, size: DefaultSize, importedThemes: [], integrationConsent: false, integrationInstalled: false }

    var theme = raw.theme ? normalizedTheme(raw.theme) : (raw.manualTheme ? normalizedTheme(raw.manualTheme) : null)
    var size = validSize(raw.size !== undefined ? raw.size : raw.manualSize, DefaultSize)
    var importedThemes = Array.isArray(raw.importedThemes) ? raw.importedThemes.slice(0, 1024) : []
    var integrationConsent = Boolean(raw.integrationConsent)
    var integrationInstalled = Boolean(raw.integrationInstalled)

    return {
      ok: true,
      reason: "",
      theme: theme,
      size: size,
      importedThemes: importedThemes,
      integrationConsent: integrationConsent,
      integrationInstalled: integrationInstalled
    }
  } catch (error) {
    return { ok: false, reason: "corrupt", theme: null, size: DefaultSize, importedThemes: [], integrationConsent: false, integrationInstalled: false }
  }
}

function stateDocument(arg1, arg2, arg3, arg4, arg5) {
  var doc = { version: 2 }
  if (typeof arg1 === "object" && arg1 !== null && !arg1.displayName && !arg1.hyprcursor && !arg1.xcursor) {
    var s = arg1
    doc.theme = s.theme ? {
      displayName: sanitizeString(s.theme.displayName, 256),
      hyprcursor: sanitizeString(s.theme.hyprcursor, 256),
      xcursor: sanitizeString(s.theme.xcursor, 256)
    } : null
    doc.size = validSize(s.size !== undefined ? s.size : s.manualSize, DefaultSize)
    doc.importedThemes = Array.isArray(s.importedThemes) ? s.importedThemes.slice(0, 1024) : []
    doc.integrationConsent = Boolean(s.integrationConsent)
    doc.integrationInstalled = Boolean(s.integrationInstalled)
  } else {
    var theme = arg1
    var size = validSize(arg2, DefaultSize)
    var importedThemes = Array.isArray(arg3) ? arg3.slice(0, 1024) : []
    doc.theme = theme ? {
      displayName: sanitizeString(theme.displayName, 256),
      hyprcursor: sanitizeString(theme.hyprcursor, 256),
      xcursor: sanitizeString(theme.xcursor, 256)
    } : null
    doc.size = size
    doc.importedThemes = importedThemes
    doc.integrationConsent = Boolean(arg4)
    doc.integrationInstalled = Boolean(arg5)
  }
  return JSON.stringify(doc, null, 2) + "\n"
}

function findTheme(themes, wanted) {
  if (!wanted || !Array.isArray(themes)) return null
  var isStr = typeof wanted === "string"
  var wantedName = (isStr ? wanted : sanitizeString(wanted.displayName, 256)).toLowerCase()
  var wantedHypr = (isStr ? wanted : sanitizeString(wanted.hyprcursor, 256)).toLowerCase()
  var wantedX = (isStr ? wanted : sanitizeString(wanted.xcursor, 256)).toLowerCase()
  var wantedId = (isStr ? wanted : sanitizeString(wanted.id, 256)).toLowerCase()
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
  var current = sanitizeString(currentXcursor, 256).toLowerCase()
  if (current && Array.isArray(themes)) {
    for (var i = 0; i < themes.length; i++) {
      if (sanitizeString(themes[i].xcursor, 256).toLowerCase() === current ||
          sanitizeString(themes[i].hyprcursor, 256).toLowerCase() === current ||
          sanitizeString(themes[i].displayName, 256).toLowerCase() === current) {
        return themes[i]
      }
    }
  }
  return (Array.isArray(themes) && themes.length > 0) ? themes[0] : null
}

function themeEquals(a, b) {
  if (!a || !b) return false
  return (sanitizeString(a.id, 256) === sanitizeString(b.id, 256) && sanitizeString(a.id, 256) !== "") ||
         (sanitizeString(a.displayName, 256) === sanitizeString(b.displayName, 256) && sanitizeString(a.displayName, 256) !== "") ||
         (sanitizeString(a.hyprcursor, 256) === sanitizeString(b.hyprcursor, 256) && sanitizeString(a.hyprcursor, 256) !== "") ||
         (sanitizeString(a.xcursor, 256) === sanitizeString(b.xcursor, 256) && sanitizeString(a.xcursor, 256) !== "")
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
  sanitizeString: sanitizeString,
  safeString: safeString,
  isInternalTheme: isInternalTheme,
  isThemeVisible: isThemeVisible,
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
