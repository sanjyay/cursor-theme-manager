import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "CursorModel.js" as Model

Item {
  id: root

  property var shell: null
  property var manifest: null
  readonly property string pluginRoot: manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
  readonly property string helperPath: pluginRoot + "/scripts/cursorctl"
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || ((Quickshell.env("HOME") || "") + "/.config")
  readonly property string stateDir: configHome + "/omarchy"
  readonly property string statePath: stateDir + "/cursor-switcher.json"

  property var themes: []
  property var committedTheme: null
  property int committedSize: 16
  property var importedThemes: []
  property var currentRoles: ({})

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
  property var _loadedState: ({ ok: false, reason: "missing", theme: null, size: 16 })
  property string _installError: ""
  property var _queuedApply: null
  property var _activeApply: null
  property string _applyStdout: ""
  property string _applyStderr: ""
  property var _debouncedPreview: null
  property string _discoverOutput: ""
  property string _discoverError: ""
  property bool _savePending: false

  signal themesChangedByScan()
  signal importCompleted(var theme, string message)
  signal importFailed(string error)

  // In-App File Browser State
  property string browserPath: ""
  property var browserEntries: []
  property var browserBreadcrumbs: []
  property bool browserCanGoUp: false
  property string browserParent: ""
  property bool browserLoading: false
  property string browserError: ""

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
      isEnabled = shell.pluginRegistry.isEnabled(manifest && manifest.id ? manifest.id : "goblin.cursor-switcher")
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
      lastError = ""
      themesChangedByScan()
      if (!ready) {
        initialize(parsed.currentXcursor || "")
      } else if (committedTheme) {
        fetchRoles(committedTheme.displayName || committedTheme.id, committedTheme.path || "")
      }
    } catch (error) {
      lastError = "Cursor discovery returned invalid data"
      console.warn("goblin.cursor-switcher: discovery parse failed:", error)
    }
  }

  function fetchRoles(themeIdentifier, themePath) {
    if (!themeIdentifier || fetchRolesProcess.running) return
    var args = [helperPath, "get-preview-roles", "--theme", String(themeIdentifier)]
    if (themePath) {
      args.push("--path", String(themePath))
    }
    fetchRolesProcess.command = args
    fetchRolesProcess.running = true
  }

  function initialize(currentXcursor) {
    if (ready || !_stateLoaded || !_scanLoaded) return

    committedSize = Model.validSize(_loadedState.size)
    importedThemes = _loadedState.importedThemes || []

    var found = _loadedState.ok ? Model.findTheme(themes, _loadedState.theme) : null
    if (!found) found = Model.fallbackTheme(themes, currentXcursor)
    committedTheme = found

    ready = true
    statusText = themes.length ? themes.length + " cursor themes" : "No cursor themes found"

    if (_loadedState.ok && !found) {
      lastError = "The saved cursor theme is no longer installed"
    } else if (_loadedState.reason === "corrupt" || _loadedState.reason === "invalid") {
      lastError = "The saved cursor settings were invalid; using a safe fallback"
    }

    if (committedTheme) {
      enqueueApply(committedTheme, committedSize, "restore")
      fetchRoles(committedTheme.displayName || committedTheme.id, committedTheme.path || "")
    }
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
    committedTheme = theme
    enqueueApply(theme, committedSize, "commit")
    fetchRoles(theme.displayName || theme.id, theme.path || "")
    persistState()
  }

  function commitSize(size) {
    previewTimer.stop()
    _debouncedPreview = null
    committedSize = Model.validSize(size)
    if (committedTheme) enqueueApply(committedTheme, committedSize, "commit")
    persistState()
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
      committedTheme,
      committedSize,
      importedThemes
    )
    stateFile.setText(doc)
  }

  function indexOfCommitted() {
    if (!committedTheme) return -1
    for (var i = 0; i < themes.length; i++) {
      if (Model.themeEquals(themes[i], committedTheme)) return i
    }
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
    chooseFileProcess.running = true
  }

  function importTheme(sourcePath, optionalName) {
    if (!sourcePath || importProcess.running) return
    lastError = ""
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
    if (committedTheme && (committedTheme.id === theme.id || committedTheme.displayName === theme.displayName)) {
      var fb = Model.fallbackTheme(themes, "Banana")
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
        console.warn("goblin.cursor-switcher:", root._installError)
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
        console.warn("goblin.cursor-switcher: app registration failed:",
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
        console.warn("goblin.cursor-switcher:", root.lastError)
      }
    }
  }

  Process {
    id: fetchRolesProcess
    running: false
    command: []
    stdout: StdioCollector { id: fetchRolesStdout; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode === 0) {
        try {
          var res = JSON.parse(fetchRolesStdout.text || "{}")
          if (res && typeof res === "object") {
            root.currentRoles = res
          }
        } catch (e) {
          console.warn("goblin.cursor-switcher: failed to parse preview roles output:", e)
        }
      }
    }
  }

  function browseDirectory(path) {
    if (listDirProcess.running) return
    browserLoading = true
    browserError = ""
    var target = path ? String(path) : (browserPath || "")
    listDirProcess.command = [helperPath, "list-dir", "--path", target]
    listDirProcess.running = true
  }

  Process {
    id: listDirProcess
    running: false
    command: []
    stdout: StdioCollector { id: listDirStdout; waitForEnd: true }
    stderr: StdioCollector { id: listDirStderr; waitForEnd: true }
    onExited: function(exitCode) {
      root.browserLoading = false
      var raw = String(listDirStdout.text || "").trim()
      if (exitCode === 0 && raw) {
        try {
          var parsed = JSON.parse(raw)
          if (parsed.ok) {
            root.browserPath = parsed.path || ""
            root.browserParent = parsed.parent || ""
            root.browserCanGoUp = Boolean(parsed.can_go_up)
            root.browserBreadcrumbs = parsed.breadcrumbs || []
            root.browserEntries = parsed.entries || []
            root.browserError = ""
          } else {
            root.browserError = parsed.error || "Cannot read directory"
          }
        } catch (e) {
          root.browserError = "Failed to parse directory listing"
        }
      } else {
        root.browserError = root.elide(listDirStderr.text || "Cannot access folder")
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
          var msg = parsed.alreadyImported ? "Already imported: " + parsed.theme.displayName : "Successfully imported " + parsed.theme.displayName
          root.statusText = msg
          root.lastError = ""
          root.refresh(true)
          var importedObj = Model.normalizedTheme(parsed.theme)
          if (importedObj) {
            root.commitTheme(importedObj)
          }
          root.importCompleted(parsed.theme, msg)
        } else {
          var err = parsed.error || "Failed to import cursor theme"
          root.lastError = err
          root.statusText = "Import failed"
          root.importFailed(err)
        }
      } catch (e) {
        var errText = root.elide(importStderr.text || raw || "Import failed")
        root.lastError = errText
        root.statusText = "Import failed"
        root.importFailed(errText)
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
        console.warn("goblin.cursor-switcher:", root.lastError)
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
