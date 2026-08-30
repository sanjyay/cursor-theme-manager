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
  readonly property string bananaPackage: pluginRoot + "/themes/banana/generated/Banana"
  readonly property string bananaPreview: pluginRoot + "/themes/banana/upstream/svg/left_ptr.svg"
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || ((Quickshell.env("HOME") || "") + "/.config")
  readonly property string stateDir: configHome + "/omarchy"
  readonly property string statePath: stateDir + "/cursor-switcher.json"
  readonly property string installTarget: (Quickshell.env("XDG_DATA_HOME") || ((Quickshell.env("HOME") || "") + "/.local/share")) + "/icons/Banana"

  property var themes: []
  property var committedTheme: null
  property int committedSize: 16
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
    installProcess.command = [sourceRoot + "/scripts/cursorctl", "install-bundled",
      "--themes-dir", sourceRoot + "/themes", "--version", String(manifest.version || "1")]
    installProcess.running = true
  }

  onManifestChanged: startupTimer.restart()
  Component.onCompleted: startupTimer.restart()
  Component.onDestruction: {
    var sourceRoot = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : (root.pluginRoot || "")
    if (sourceRoot !== "") {
      Util.execDetached(Util.shellQuote(sourceRoot + "/scripts/cursorctl") + " unregister-app")
      Util.execDetached(Util.shellQuote(sourceRoot + "/scripts/cursorctl") + " reset-defaults")
    }
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
      console.warn("goblin.cursor-switcher: discovery parse failed:", error)
    }
  }

  function initialize(currentXcursor) {
    if (ready || !_stateLoaded || !_scanLoaded) return
    var selected = _loadedState.ok ? Model.findTheme(themes, _loadedState.theme) : null
    if (!selected) selected = Model.fallbackTheme(themes, currentXcursor)
    committedTheme = selected
    committedSize = Model.validSize(_loadedState.size)
    ready = true
    statusText = themes.length ? themes.length + " cursor themes" : "No cursor themes found"
    if (_loadedState.ok && !Model.findTheme(themes, _loadedState.theme)) {
      lastError = "The saved cursor theme is no longer installed"
    } else if (_loadedState.reason === "corrupt" || _loadedState.reason === "invalid") {
      lastError = "The saved cursor settings were invalid; using a safe fallback"
    }
    if (_loadedState.ok && selected) enqueueApply(selected, committedSize, "restore")
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
    enqueueApply(theme, committedSize, "commit")
  }

  function commitSize(size) {
    if (!committedTheme) return
    previewTimer.stop()
    _debouncedPreview = null
    enqueueApply(committedTheme, Model.validSize(size), "commit")
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

  function persistCommitted() {
    if (!committedTheme) return
    if (!stateDirReady) { _savePending = true; return }
    _savePending = false
    stateFile.setText(Model.stateDocument(committedTheme, committedSize))
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

  Process {
    id: stateDirProcess
    command: ["mkdir", "-p", root.stateDir]
    property bool complete: false
    onExited: function(exitCode) {
      complete = true
      root.stateDirReady = exitCode === 0
      if (!root.stateDirReady) root.lastError = "Could not create the cursor settings directory"
      else if (root._savePending) root.persistCommitted()
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
        console.warn("goblin.cursor-switcher: apply failed:", root.lastError)
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
          root.persistCommitted()
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
