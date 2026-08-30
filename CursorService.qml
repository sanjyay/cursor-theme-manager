import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "CursorModel.js" as Model
import "ThemeCursorMappings.js" as Mappings

Item {
  id: root

  property var shell: null
  property var manifest: null
  readonly property string pluginRoot: manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
  readonly property string helperPath: pluginRoot + "/scripts/cursorctl"
  readonly property string bananaPackage: pluginRoot + "/themes/banana/generated/Banana"
  readonly property string bananaPreview: pluginRoot + "/themes/banana/upstream/svg/left_ptr.svg"
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || ((Quickshell.env("HOME") || "") + "/.config")
  readonly property string stateDir: configHome + "/omarchy"
  readonly property string statePath: stateDir + "/cursor-switcher.json"

  // Mode: "manual" | "follow-omarchy"
  property string mode: "manual"
  property var themes: []
  property var committedTheme: null
  property int committedSize: 16

  // Independent manual and follow states
  property var manualTheme: null
  property int manualSize: 16
  property int followSize: 16
  property var followMappings: ({})
  property var importedThemes: []

  // Active Omarchy Theme tracking
  property string currentOmarchyTheme: ""
  property string currentOmarchyThemeDisplay: ""
  property var activeMappingInfo: null

  // Preview & Operation State
  property var previewTheme: null
  property int previewSize: 0
  property bool ready: false
  property bool scanning: false
  property bool applying: false
  property string lastError: ""
  property string statusText: "Starting…"
  property double lastScanMs: 0

  property bool _started: false
  property bool _stateLoaded: false
  property bool _scanLoaded: false
  property var _loadedState: ({ ok: false, reason: "missing", mode: "manual", theme: null, size: 16 })
  property string _installError: ""
  property var _queuedApply: null
  property var _activeApply: null
  property string _applyStdout: ""
  property string _applyStderr: ""
  property var _debouncedPreview: null
  property string _discoverOutput: ""
  property string _discoverError: ""
  property bool _savePending: false

  readonly property bool previewActive: previewTheme !== null
  readonly property var sizes: Model.SupportedSizes
  signal themesChangedByScan()

  function elide(value) {
    var text = String(value || "").replace(/\s+/g, " ").trim()
    return text.length > 180 ? text.substring(0, 177) + "…" : text
  }

  function start() {
    if (_started) return
    var sourceRoot = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
    if (sourceRoot === "") { startupTimer.restart(); return }
    _started = true
    stateDirProcess.running = true
    snapshotProcess.command = [sourceRoot + "/scripts/cursorctl", "snapshot-original-state"]
    snapshotProcess.running = true
  }

  onManifestChanged: startupTimer.restart()
  Component.onCompleted: startupTimer.restart()
  Component.onDestruction: {
    var isEnabled = false
    if (shell && shell.pluginRegistry && typeof shell.pluginRegistry.isEnabled === "function") {
      isEnabled = shell.pluginRegistry.isEnabled("sanjyay.cursor-switcher")
    } else if (manifest && manifest.id && shell && shell.pluginRegistry) {
      isEnabled = shell.pluginRegistry.isEnabled(manifest.id)
    }
    if (isEnabled) {
      return
    }
    var dataHome = Quickshell.env("XDG_DATA_HOME") || ((Quickshell.env("HOME") || "") + "/.local/share")
    var cleanupPath = dataHome + "/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup"
    var sourceRoot = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : (root.pluginRoot || "")
    Util.execDetached(Util.shellQuote(cleanupPath) + " on-destroy --plugin-dir " + Util.shellQuote(sourceRoot))
  }

  Timer { id: startupTimer; interval: 25; repeat: false; onTriggered: root.start() }

  function refresh(force) {
    if (!_started || scanning || discoverProcess.running) return
    if (!force && lastScanMs > 0 && Date.now() - lastScanMs < 30000) return
    scanning = true
    _discoverOutput = ""
    _discoverError = ""
    discoverProcess.command = [helperPath, "discover"]
    discoverProcess.running = true
  }

  function refreshIfStale() { refresh(false) }

  function parseDiscovery(raw) {
    try {
      var parsed = JSON.parse(String(raw || ""))
      themes = Model.normalizeThemes(parsed.themes)
      lastScanMs = Date.now()
      _scanLoaded = true
      themesChangedByScan()
      initialize(parsed.currentXcursor || "")
    } catch (error) {
      lastError = "Cursor discovery returned invalid data"
      console.warn("sanjyay.cursor-switcher: discovery parse failed:", error)
    }
  }

  function onOmarchyThemeChanged(rawThemeName) {
    var raw = String(rawThemeName || "").trim()
    root.currentOmarchyTheme = raw
    root.currentOmarchyThemeDisplay = Mappings.formatOmarchyThemeName(raw)
    var res = Mappings.resolveMappedTheme(raw, root.followMappings, root.themes, "Adwaita")
    root.activeMappingInfo = res

    if (root.mode === "follow-omarchy" && root.ready && res && res.theme) {
      if (root.committedTheme !== res.theme || root.committedSize !== root.followSize) {
        root.enqueueApply(res.theme, root.followSize, "commit")
      }
    }
  }

  function initialize(currentXcursor) {
    if (ready || !_stateLoaded || !_scanLoaded) return

    mode = _loadedState.mode || "manual"
    manualSize = Model.validSize(_loadedState.manualSize)
    followSize = Model.validSize(_loadedState.followSize)
    followMappings = _loadedState.follow && _loadedState.follow.mappings ? _loadedState.follow.mappings : ({})
    importedThemes = _loadedState.importedThemes || []

    var manual = _loadedState.ok ? Model.findTheme(themes, _loadedState.manualTheme || _loadedState.theme) : null
    if (!manual) manual = Model.fallbackTheme(themes, currentXcursor)
    manualTheme = manual

    // Read current Omarchy theme
    var res = Mappings.resolveMappedTheme(currentOmarchyTheme, followMappings, themes, "Adwaita")
    activeMappingInfo = res

    if (mode === "follow-omarchy") {
      var mapped = res && res.theme ? res.theme : manual
      committedTheme = mapped
      committedSize = followSize
    } else {
      committedTheme = manual
      committedSize = manualSize
    }

    ready = true
    statusText = themes.length ? themes.length + " cursor themes" : "No cursor themes found"

    if (_loadedState.ok && !manual) {
      lastError = "The saved cursor theme is no longer installed"
    } else if (_loadedState.reason === "corrupt" || _loadedState.reason === "invalid") {
      lastError = "The saved cursor settings were invalid; using a safe fallback"
    }

    if (committedTheme) {
      enqueueApply(committedTheme, committedSize, "restore")
    }
  }

  function setMode(newMode) {
    if (newMode !== "manual" && newMode !== "follow-omarchy") return
    if (newMode === mode) return
    mode = newMode

    if (mode === "follow-omarchy") {
      var res = Mappings.resolveMappedTheme(currentOmarchyTheme, followMappings, themes, "Adwaita")
      activeMappingInfo = res
      var targetTheme = (res && res.theme) ? res.theme : (manualTheme || committedTheme)
      if (targetTheme) {
        enqueueApply(targetTheme, followSize, "commit")
      }
    } else {
      // Switching back to manual mode: restore manualTheme at manualSize
      var targetTheme = manualTheme || committedTheme
      if (targetTheme) {
        enqueueApply(targetTheme, manualSize, "commit")
      }
    }
    persistState()
  }

  function requestPreview(theme, size) {
    if (!ready || !theme || !theme.previewable) return
    _debouncedPreview = { theme: theme, size: Model.validSize(size === undefined ? committedSize : size) }
    previewTimer.restart()
  }

  function cancelPreview() {
    previewTimer.stop()
    _debouncedPreview = null
    if (!previewActive && !(_activeApply && _activeApply.kind === "preview")) return
    enqueueApply(committedTheme, committedSize, "cancel")
  }

  function commitTheme(theme) {
    if (!theme) return
    previewTimer.stop()
    _debouncedPreview = null

    if (mode === "manual") {
      manualTheme = theme
      enqueueApply(theme, manualSize, "commit")
    } else {
      // In follow mode: clicking a theme card sets mapping for active Omarchy theme
      var normId = Mappings.normalizeOmarchyThemeId(currentOmarchyTheme)
      var nextMappings = Object.assign({}, followMappings)
      nextMappings[normId] = theme.displayName
      followMappings = nextMappings
      var res = Mappings.resolveMappedTheme(currentOmarchyTheme, followMappings, themes, "Adwaita")
      activeMappingInfo = res
      enqueueApply(theme, followSize, "commit")
    }
  }

  function commitSize(size) {
    if (!committedTheme) return
    previewTimer.stop()
    _debouncedPreview = null
    var valid = Model.validSize(size)

    if (mode === "manual") {
      manualSize = valid
      enqueueApply(committedTheme, manualSize, "commit")
    } else {
      followSize = valid
      enqueueApply(committedTheme, followSize, "commit")
    }
  }

  function enqueueApply(theme, size, kind) {
    if (!theme) return
    _queuedApply = { theme: theme, size: Model.validSize(size), kind: kind }
    if (!applyProcess.running) startQueuedApply()
  }

  function startQueuedApply() {
    if (!_queuedApply || applyProcess.running) return
    _activeApply = _queuedApply
    _queuedApply = null
    _applyStdout = ""
    _applyStderr = ""
    applying = true
    applyProcess.command = Model.applyArguments(helperPath, _activeApply.theme, _activeApply.size,
      _activeApply.kind === "preview")
    applyProcess.running = true
  }

  function persistState() {
    if (!stateDirReady) { _savePending = true; return }
    _savePending = false
    var doc = Model.stateDocument(
      mode,
      manualTheme || committedTheme,
      manualSize,
      followSize,
      followMappings,
      importedThemes,
      committedTheme
    )
    stateFile.setText(doc)
  }

  function indexOfCommitted() {
    if (!committedTheme) return -1
    for (var i = 0; i < themes.length; i++)
      if (Model.findTheme([themes[i]], committedTheme)) return i
    return -1
  }

  function themeSummary(theme) {
    if (!theme) return "Unavailable"
    if (theme.subtitle) return theme.subtitle
    if (theme.formats.length === 2) return "Hyprcursor + XCursor"
    return theme.formats[0] === "hyprcursor" ? "Hyprcursor" : "XCursor"
  }

  function restoreConfigured() {
    if (committedTheme) enqueueApply(committedTheme, committedSize, "restore")
  }

  // File Chooser & Import API
  function chooseAndImportFile() {
    if (chooseFileProcess.running || importProcess.running) return
    chooseFileStdout.text = ""
    chooseFileProcess.running = true
  }

  function importTheme(sourcePath, optionalName) {
    if (!sourcePath || importProcess.running) return
    lastError = ""
    importStdout.text = ""
    importStderr.text = ""
    statusText = "Importing theme…"
    var args = [helperPath, "import", "--source", sourcePath]
    if (optionalName) {
      args.push("--name", String(optionalName))
    }
    importProcess.command = args
    importProcess.running = true
  }

  function removeImportedTheme(theme) {
    if (!theme || !theme.id || removeImportProcess.running) return
    if (!theme.imported && theme.sourceType !== "imported") return
    lastError = ""
    // If active, switch safely to fallback first
    if (committedTheme && (committedTheme.id === theme.id || committedTheme.displayName === theme.displayName)) {
      var fb = Model.fallbackTheme(themes, "Adwaita")
      if (fb) enqueueApply(fb, committedSize, "commit")
    }
    removeImportProcess.command = [helperPath, "remove-imported", "--id", theme.id]
    removeImportProcess.running = true
  }

  Process {
    id: stateDirProcess
    command: ["mkdir", "-p", root.stateDir]
    property bool complete: false
    onExited: function(exitCode) {
      complete = true
      root.stateDirReady = exitCode === 0
      if (!root.stateDirReady) root.lastError = "Could not create the cursor settings directory"
      else if (root._savePending) root.persistState()
    }
  }
  property bool stateDirReady: false

  FileView {
    id: omarchyThemeFile
    path: (Quickshell.env("HOME") || "") + "/.local/state/omarchy/current/theme.name"
    watchChanges: true
    printErrors: false
    onLoaded: function(t) { root.onOmarchyThemeChanged(t) }
    onFileChanged: function(t) { root.onOmarchyThemeChanged(t) }
  }

  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: false
    atomicWrites: true
    printErrors: false
    onLoaded: {
      root._loadedState = Model.parseState(text())
      root._stateLoaded = true
      root.initialize("")
    }
    onLoadFailed: {
      root._loadedState = Model.parseState("")
      root._stateLoaded = true
      root.initialize("")
    }
  }

  Process {
    id: snapshotProcess
    running: false
    command: []
    onExited: function(exitCode) {
      cleanupHelperProcess.command = [root.helperPath, "install-cleanup-helper",
        "--source", root.pluginRoot]
      cleanupHelperProcess.running = true
    }
  }

  Process {
    id: cleanupHelperProcess
    running: false
    command: []
    onExited: function(exitCode) {
      installProcess.command = [root.helperPath, "install-bundled",
        "--themes-dir", root.pluginRoot + "/themes", "--version", String((root.manifest && root.manifest.version) || "1")]
      installProcess.running = true
    }
  }

  Process {
    id: installProcess
    running: false
    command: []
    stderr: StdioCollector { id: installStderr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root._installError = root.elide(installStderr.text || "Bundled theme installation failed")
        root.lastError = root._installError
        console.warn("sanjyay.cursor-switcher:", root._installError)
      }
      registerAppProcess.command = [root.helperPath, "register-app",
        "--source", root.pluginRoot]
      registerAppProcess.running = true
    }
  }

  Process {
    id: registerAppProcess
    running: false
    command: []
    stderr: StdioCollector { id: registerAppStderr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        console.warn("sanjyay.cursor-switcher: app registration failed:",
          root.elide(registerAppStderr.text || "unknown error"))
      }
      root.refresh(true)
    }
  }

  Process {
    id: discoverProcess
    running: false
    command: []
    stdout: StdioCollector { id: discoverStdout; waitForEnd: true; onStreamFinished: root._discoverOutput = text }
    stderr: StdioCollector { id: discoverStderr; waitForEnd: true; onStreamFinished: root._discoverError = text }
    onExited: function(exitCode) {
      root.scanning = false
      if (exitCode === 0) root.parseDiscovery(discoverStdout.text || root._discoverOutput)
      else {
        root.lastError = root.elide(discoverStderr.text || root._discoverError || "Cursor discovery failed")
        console.warn("sanjyay.cursor-switcher:", root.lastError)
      }
    }
  }

  Process {
    id: chooseFileProcess
    running: false
    command: [root.helperPath, "choose-file"]
    stdout: StdioCollector { id: chooseFileStdout; waitForEnd: true }
    onExited: function(exitCode) {
      var selected = String(chooseFileStdout.text || "").trim()
      if (exitCode === 0 && selected.length > 0) {
        root.importTheme(selected)
      }
    }
  }

  Process {
    id: importProcess
    running: false
    command: []
    stdout: StdioCollector { id: importStdout; waitForEnd: true }
    stderr: StdioCollector { id: importStderr; waitForEnd: true }
    onExited: function(exitCode) {
      var raw = String(importStdout.text || "").trim()
      try {
        var parsed = JSON.parse(raw)
        if (parsed.ok && parsed.theme) {
          root.statusText = parsed.alreadyImported ? "Already imported: " + parsed.theme.displayName : "Successfully imported " + parsed.theme.displayName
          root.refresh(true)
          // Automatically select/commit imported theme
          var importedObj = Model.normalizedTheme(parsed.theme)
          if (importedObj) {
            root.commitTheme(importedObj)
          }
        } else {
          root.lastError = parsed.error || "Failed to import cursor theme"
          root.statusText = "Import failed"
        }
      } catch (e) {
        root.lastError = root.elide(importStderr.text || raw || "Import failed")
        root.statusText = "Import failed"
      }
    }
  }

  Process {
    id: removeImportProcess
    running: false
    command: []
    onExited: function(exitCode) {
      if (exitCode === 0) {
        root.statusText = "Imported theme removed"
        root.refresh(true)
      } else {
        root.lastError = "Could not remove imported theme"
      }
    }
  }

  Timer {
    id: previewTimer
    interval: 120
    repeat: false
    onTriggered: if (root._debouncedPreview) {
      var request = root._debouncedPreview
      root._debouncedPreview = null
      root.enqueueApply(request.theme, request.size, "preview")
    }
  }

  Process {
    id: applyProcess
    running: false
    command: []
    stdout: StdioCollector { id: applyStdout; waitForEnd: true; onStreamFinished: root._applyStdout = text }
    stderr: StdioCollector { id: applyStderr; waitForEnd: true; onStreamFinished: root._applyStderr = text }
    onExited: function(exitCode) {
      var request = root._activeApply
      root.applying = false
      if (exitCode !== 0) {
        root.lastError = root.elide(applyStderr.text || root._applyStderr || applyStdout.text || root._applyStdout || "Cursor could not be applied")
        console.warn("sanjyay.cursor-switcher: apply failed:", root.lastError)
        if (request && request.kind === "commit") {
          root.statusText = "Failed to switch to " + request.theme.displayName
        } else if (request && request.kind === "preview") {
          root.previewTheme = null
          root.previewSize = 0
          root.statusText = "Preview unavailable for " + request.theme.displayName
        }
      } else if (request) {
        root.lastError = ""
        if (request.kind === "preview") {
          root.previewTheme = request.theme
          root.previewSize = request.size
          root.statusText = "Previewing " + request.theme.displayName
        } else if (request.kind === "commit") {
          root.committedTheme = request.theme
          root.committedSize = request.size
          root.previewTheme = null
          root.previewSize = 0
          root.persistState()
          root.statusText = request.theme.displayName + " · " + request.size + " px"
        } else {
          root.previewTheme = null
          root.previewSize = 0
          root.statusText = root.committedTheme ? root.committedTheme.displayName + " · " + root.committedSize + " px" : "Ready"
        }
      }
      root._activeApply = null
      root.startQueuedApply()
    }
  }
}
