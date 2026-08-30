.pragma library

var SupportedSizes = [16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256]
var DefaultSize = 16

var VisibleThemes = [
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

function visibleThemeIndex(theme) {
  if (!theme) return -1
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

  return {
    id: safeString(raw.id) || hypr || xcursor,
    displayName: safeString(raw.displayName) || hypr || xcursor,
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

function themeKey(theme) {
  if (!theme) return ""
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
    mode: "manual",
    theme: null,
    size: DefaultSize,
    manualTheme: null,
    manualSize: DefaultSize,
    followSize: DefaultSize,
    follow: { defaultTheme: "Adwaita", mappings: {} },
    importedThemes: []
  }
  if (!safeString(text).trim()) return fallback
  try {
    var raw = JSON.parse(text)
    if (!raw || typeof raw !== "object") return { ok: false, reason: "invalid", mode: "manual", theme: null, size: DefaultSize, manualTheme: null, manualSize: DefaultSize, followSize: DefaultSize, follow: { defaultTheme: "Adwaita", mappings: {} }, importedThemes: [] }

    var mode = raw.mode === "follow-omarchy" ? "follow-omarchy" : "manual"
    var manualTheme = raw.manualTheme ? normalizedTheme(raw.manualTheme) : (raw.theme ? normalizedTheme(raw.theme) : null)
    var manualSize = validSize(raw.manualSize !== undefined ? raw.manualSize : raw.size, DefaultSize)
    var followSize = validSize(raw.followSize !== undefined ? raw.followSize : raw.size, DefaultSize)

    var follow = {
      defaultTheme: (raw.follow && raw.follow.defaultTheme) || "Adwaita",
      mappings: (raw.follow && typeof raw.follow.mappings === "object" && raw.follow.mappings) ? raw.follow.mappings : {}
    }
    var importedThemes = Array.isArray(raw.importedThemes) ? raw.importedThemes : []

    var effectiveTheme = manualTheme
    var effectiveSize = mode === "follow-omarchy" ? followSize : manualSize

    return {
      ok: true,
      reason: "",
      mode: mode,
      theme: effectiveTheme,
      size: effectiveSize,
      manualTheme: manualTheme,
      manualSize: manualSize,
      followSize: followSize,
      follow: follow,
      importedThemes: importedThemes
    }
  } catch (error) {
    return { ok: false, reason: "corrupt", mode: "manual", theme: null, size: DefaultSize, manualTheme: null, manualSize: DefaultSize, followSize: DefaultSize, follow: { defaultTheme: "Adwaita", mappings: {} }, importedThemes: [] }
  }
}

function stateDocument(arg1, arg2, arg3, arg4, arg5, arg6, arg7) {
  var doc = { version: 2 }
  if (typeof arg1 === "object" && arg1 !== null && !arg1.displayName && !arg1.hyprcursor && !arg1.xcursor) {
    var s = arg1
    doc.mode = s.mode === "follow-omarchy" ? "follow-omarchy" : "manual"
    doc.manualTheme = s.manualTheme ? {
      displayName: s.manualTheme.displayName,
      hyprcursor: s.manualTheme.hyprcursor,
      xcursor: s.manualTheme.xcursor
    } : null
    doc.manualSize = validSize(s.manualSize, DefaultSize)
    doc.followSize = validSize(s.followSize, DefaultSize)
    doc.theme = s.theme ? {
      displayName: s.theme.displayName,
      hyprcursor: s.theme.hyprcursor,
      xcursor: s.theme.xcursor
    } : doc.manualTheme
    doc.size = validSize(s.size, (doc.mode === "follow-omarchy" ? doc.followSize : doc.manualSize))
    doc.follow = s.follow || { defaultTheme: "Adwaita", mappings: {} }
    doc.importedThemes = s.importedThemes || []
  } else if (typeof arg1 === "string" && (arg1 === "manual" || arg1 === "follow-omarchy")) {
    var mode = arg1
    var manualTheme = arg2
    var manualSize = validSize(arg3, DefaultSize)
    var followSize = validSize(arg4, DefaultSize)
    var followMappings = arg5 || {}
    var importedThemes = arg6 || []
    var activeTheme = arg7 || manualTheme

    doc.mode = mode
    doc.manualTheme = manualTheme ? {
      displayName: manualTheme.displayName,
      hyprcursor: manualTheme.hyprcursor,
      xcursor: manualTheme.xcursor
    } : null
    doc.manualSize = manualSize
    doc.followSize = followSize
    doc.theme = activeTheme ? {
      displayName: activeTheme.displayName,
      hyprcursor: activeTheme.hyprcursor,
      xcursor: activeTheme.xcursor
    } : doc.manualTheme
    doc.size = mode === "follow-omarchy" ? followSize : manualSize
    doc.follow = {
      defaultTheme: "Adwaita",
      mappings: followMappings
    }
    doc.importedThemes = importedThemes
  } else {
    var theme = arg1
    var size = validSize(arg2, DefaultSize)
    doc.mode = "manual"
    doc.theme = theme ? {
      displayName: theme.displayName,
      hyprcursor: theme.hyprcursor,
      xcursor: theme.xcursor
    } : null
    doc.size = size
    doc.manualTheme = doc.theme
    doc.manualSize = size
    doc.followSize = size
    doc.follow = { defaultTheme: "Adwaita", mappings: {} }
    doc.importedThemes = []
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

if (typeof module !== "undefined") module.exports = {
  SupportedSizes: SupportedSizes,
  DefaultSize: DefaultSize,
  VisibleThemes: VisibleThemes,
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
  applyArguments: applyArguments,
  initialPreviewState: initialPreviewState,
  startPreview: startPreview,
  cancelPreview: cancelPreview,
  commitPreview: commitPreview
}
