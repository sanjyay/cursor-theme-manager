.pragma library

var SupportedSizes = [16, 20, 24, 28, 32, 40, 48]

function safeString(value) {
  return value === undefined || value === null ? "" : String(value)
}

function validSize(value) {
  var n = Number(value)
  return SupportedSizes.indexOf(n) !== -1 ? n : 24
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
  return {
    displayName: safeString(raw.displayName) || hypr || xcursor,
    hyprcursor: hypr,
    xcursor: xcursor,
    path: safeString(raw.path),
    formats: formats,
    previewPath: safeString(raw.previewPath),
    bundled: raw.bundled === true,
    previewable: hypr !== ""
  }
}

function themeKey(theme) {
  if (!theme) return ""
  return (safeString(theme.hyprcursor) || safeString(theme.xcursor) || safeString(theme.displayName)).toLowerCase()
}

function mergeTheme(a, b) {
  var preferred = b.bundled || (!a.bundled && b.path.indexOf("/.local/share/icons/") !== -1) ? b : a
  var other = preferred === a ? b : a
  var formats = preferred.formats.slice()
  other.formats.forEach(function(format) { if (formats.indexOf(format) === -1) formats.push(format) })
  return {
    displayName: preferred.displayName || other.displayName,
    hyprcursor: preferred.hyprcursor || other.hyprcursor,
    xcursor: preferred.xcursor || other.xcursor,
    path: preferred.path || other.path,
    formats: formats,
    previewPath: preferred.previewPath || other.previewPath,
    bundled: preferred.bundled || other.bundled,
    previewable: (preferred.hyprcursor || other.hyprcursor) !== ""
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
  themes.sort(function(a, b) {
    if (a.bundled !== b.bundled) return a.bundled ? -1 : 1
    return a.displayName.localeCompare(b.displayName)
  })
  return themes
}

function parseState(text) {
  var fallback = { ok: false, reason: "missing", theme: null, size: 24 }
  if (!safeString(text).trim()) return fallback
  try {
    var raw = JSON.parse(text)
    if (!raw || typeof raw !== "object") return { ok: false, reason: "invalid", theme: null, size: 24 }
    var theme = normalizedTheme(raw.theme)
    if (!theme) return { ok: false, reason: "invalid", theme: null, size: validSize(raw.size) }
    return { ok: true, reason: "", theme: theme, size: validSize(raw.size) }
  } catch (error) {
    return { ok: false, reason: "corrupt", theme: null, size: 24 }
  }
}

function stateDocument(theme, size) {
  return JSON.stringify({
    version: 1,
    theme: {
      displayName: theme.displayName,
      hyprcursor: theme.hyprcursor,
      xcursor: theme.xcursor
    },
    size: validSize(size)
  }, null, 2) + "\n"
}

function findTheme(themes, wanted) {
  if (!wanted) return null
  var wantedHypr = safeString(wanted.hyprcursor).toLowerCase()
  var wantedX = safeString(wanted.xcursor).toLowerCase()
  for (var i = 0; i < themes.length; i++) {
    var theme = themes[i]
    if (wantedHypr && theme.hyprcursor.toLowerCase() === wantedHypr) return theme
    if (wantedX && theme.xcursor.toLowerCase() === wantedX) return theme
  }
  return null
}

function fallbackTheme(themes, currentXcursor) {
  var current = safeString(currentXcursor).toLowerCase()
  for (var i = 0; i < themes.length; i++)
    if (current && themes[i].xcursor.toLowerCase() === current) return themes[i]
  for (var j = 0; j < themes.length; j++)
    if (themes[j].xcursor.toLowerCase() === "default") return themes[j]
  return themes.length ? themes[0] : null
}

function applyArguments(scriptPath, theme, size, preview) {
  if (!theme) return []
  return [scriptPath, "apply",
    "--hyprcursor", theme.hyprcursor || "-",
    "--xcursor", theme.xcursor || "-",
    "--size", String(validSize(size)),
    preview ? "--preview" : "--commit"]
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
  validSize: validSize,
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
