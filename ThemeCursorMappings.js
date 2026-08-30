.pragma library

// Canonical mapping model between Omarchy desktop themes and cursor themes
var DefaultFallbackTheme = "Adwaita"

// Initial sensible defaults for Omarchy themes mapped to guaranteed available curated/bundled cursors
var DefaultMappings = {
  // Catppuccin variants
  "catppuccin": "Bibata-Catppuccin-Mocha",
  "catppuccin-mocha": "Bibata-Catppuccin-Mocha",
  "catppuccin-latte": "Banana",
  "catppuccin-frappe": "Bibata-Catppuccin-Mocha",
  "catppuccin-macchiato": "Bibata-Catppuccin-Mocha",

  // Tokyo Night variants
  "tokyo-night": "Nordzy",
  "tokyo-night-dark": "Nordzy",
  "tokyo-night-light": "Adwaita",
  "tokyo-night-moon": "Nordzy",
  "tokyo-night-storm": "Nordzy",

  // Nord & Arctic
  "nord": "Nordzy",

  // Dark & High-contrast themes
  "matte-black": "Oreo",
  "vantablack": "Oreo",
  "ristretto": "Oreo",
  "hackerman": "Banana",

  // Colorful / Retro / Themed
  "rose-pine": "Banana",
  "gruvbox": "Capitaine",
  "everforest": "Phinger",
  "kanagawa": "Volantes",
  "aether": "Volantes",
  "ame-quattro": "Capitaine",
  "dr-doom": "Banana",
  "hermarchy": "Banana",
  "spacex-terrafab": "Phinger",
  "spider-man": "Banana",
  "steam-modern": "Capitaine",
  "tech-material": "Nordzy",
  "tech-palette": "Nordzy",

  // Light themes
  "white": "Adwaita",
  "flexoki-light": "Adwaita",
  "ethereal": "Adwaita",
  "solitude": "Nordzy"
}

function normalizeOmarchyThemeId(rawName) {
  var str = String(rawName || "").trim().toLowerCase()
  str = str.replace(/[\s_]+/g, "-")
  str = str.replace(/[^a-z0-9\-]/g, "")
  str = str.replace(/-+/g, "-")
  return str
}

function formatOmarchyThemeName(rawName) {
  var str = String(rawName || "").trim()
  if (!str) return "Unknown"
  var parts = str.split(/[\s_\-]+/)
  var formatted = []
  for (var i = 0; i < parts.length; i++) {
    if (parts[i].length > 0) {
      formatted.push(parts[i].charAt(0).toUpperCase() + parts[i].slice(1).toLowerCase())
    }
  }
  return formatted.join(" ")
}

function resolveMappedTheme(omarchyThemeRaw, userMappings, availableThemes, fallbackThemeName) {
  var normId = normalizeOmarchyThemeId(omarchyThemeRaw)
  var fallbackName = fallbackThemeName || DefaultFallbackTheme
  var mappedCursorName = ""
  var source = "fallback"

  // 1. Check user-defined mappings first
  if (userMappings && typeof userMappings === "object") {
    if (userMappings[normId]) {
      mappedCursorName = String(userMappings[normId])
      source = "user"
    } else if (userMappings[omarchyThemeRaw]) {
      mappedCursorName = String(userMappings[omarchyThemeRaw])
      source = "user"
    }
  }

  // 2. Check default built-in mappings if no user mapping
  if (!mappedCursorName && DefaultMappings[normId]) {
    mappedCursorName = DefaultMappings[normId]
    source = "default"
  }

  // 3. Resolve cursor theme object in availableThemes
  var foundTheme = null
  if (mappedCursorName && Array.isArray(availableThemes)) {
    var wanted = mappedCursorName.toLowerCase()
    for (var i = 0; i < availableThemes.length; i++) {
      var t = availableThemes[i]
      if (t && (
        String(t.displayName || "").toLowerCase() === wanted ||
        String(t.hyprcursor || "").toLowerCase() === wanted ||
        String(t.xcursor || "").toLowerCase() === wanted ||
        String(t.id || "").toLowerCase() === wanted
      )) {
        foundTheme = t
        break
      }
    }
  }

  // 4. If mapped cursor not found in availableThemes, use fallback
  if (!foundTheme && Array.isArray(availableThemes)) {
    var fbWanted = fallbackName.toLowerCase()
    for (var j = 0; j < availableThemes.length; j++) {
      var ft = availableThemes[j]
      if (ft && (
        String(ft.displayName || "").toLowerCase() === fbWanted ||
        String(ft.hyprcursor || "").toLowerCase() === fbWanted ||
        String(ft.xcursor || "").toLowerCase() === fbWanted
      )) {
        foundTheme = ft
        source = "fallback"
        break
      }
    }
    // Secondary fallback: Banana or first available
    if (!foundTheme && availableThemes.length > 0) {
      for (var k = 0; k < availableThemes.length; k++) {
        if (String(availableThemes[k].displayName || "").toLowerCase() === "banana") {
          foundTheme = availableThemes[k]
          source = "fallback"
          break
        }
      }
      if (!foundTheme) {
        foundTheme = availableThemes[0]
        source = "fallback"
      }
    }
  }

  return {
    omarchyThemeId: normId,
    omarchyThemeDisplayName: formatOmarchyThemeName(omarchyThemeRaw),
    mappedCursorName: mappedCursorName || (foundTheme ? foundTheme.displayName : fallbackName),
    theme: foundTheme,
    source: source
  }
}

if (typeof module !== "undefined") {
  module.exports = {
    DefaultFallbackTheme: DefaultFallbackTheme,
    DefaultMappings: DefaultMappings,
    normalizeOmarchyThemeId: normalizeOmarchyThemeId,
    formatOmarchyThemeName: formatOmarchyThemeName,
    resolveMappedTheme: resolveMappedTheme
  }
}
