import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "CursorModel.js" as Model

Item {
  id: root

  property var shell: null
  property var manifest: null
  readonly property string pluginRoot: (manifest && manifest.__sourceDir) ? String(manifest.__sourceDir) : ((manifest && manifest.sourceDir) ? String(manifest.sourceDir) : (Quickshell.env("HOME") + "/.config/omarchy/plugins/sanjyay.cursor-theme-manager"))
  readonly property string helperPath: pluginRoot + "/scripts/cursorctl"

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

  // Integration & Removal Lifecycle State
  property bool integrationEnabled: false
  property bool setupDismissedThisSession: false
  readonly property bool setupRequired: !integrationEnabled && !setupDismissedThisSession
  property bool integrationPromptSeen: integrationEnabled || setupDismissedThisSession
  property bool integrationLoading: false
  property string integrationError: ""
  property var integrationArtifacts: ({})
  readonly property bool launcherAdded: integrationEnabled
  readonly property bool launcherPromptSeen: integrationPromptSeen
  readonly property bool launcherLoading: integrationLoading
  readonly property string launcherError: integrationError
  property string launcherPath: "" 

  property bool _started: false
  property bool _stateLoaded: false
  property bool _scanLoaded: false
  property var _loadedState: ({ ok: false, reason: "missing", theme: null, size: 16 })
  property var _queuedApply: null

  property var _activeApply: null
  property string _applyStdout: ""
  property string _applyStderr: ""
  property var _debouncedPreview: null
  property string _discoverOutput: ""
  property string _discoverError: ""

  // Size State & Trailing-Edge Request Generation Tracking
  property int requestedSize: 16
  property int liveAppliedSize: 16
  property int _persistedSize: 16
  property int _sizeRequestGeneration: 0
  property int _activeLiveGeneration: 0

  // Theme State, Runtime Caching & Monotonic Generation Tracking
  property var runtimeThemeCache: ({})
  property var liveAppliedTheme: null
  property int _themeRequestGeneration: 0
  property int _activeThemeGeneration: 0
  property var _preparingTheme: null
  property int _preparingGeneration: 0
  property bool _pendingDiscoveryRefresh: false
  property string _pendingSelectionThemeId: ""
  property int themeModelVersion: 0

  // Trailing-edge live size apply debounce timer (90 ms quiet window)
  Timer {
    id: trailingLiveSizeTimer
    interval: 90
    repeat: false
    onTriggered: root.dispatchTrailingLiveSize()
  }

  // Silent configuration persistence timer (runs after live setcursor completes)
  Timer {
    id: commitSizeDebounceTimer
    interval: 150
    repeat: false
    onTriggered: root.flushFinalSizePersistence()
  }

  // Silent theme persistence debounce timer (200 ms quiet window)
  Timer {
    id: persistThemeDebounceTimer
    interval: 200
    repeat: false
    onTriggered: root.flushFinalThemePersistence()
  }

  signal themesChangedByScan()
  signal importCompleted(var theme, string message)
  signal importFailed(string error)
  signal launcherChanged()
  signal integrationChanged()

  // In-App File Browser State
  property string browserPath: ""
  property var browserEntries: []
  property var browserBreadcrumbs: []
  property bool browserCanGoUp: false
  property string browserParent: ""
  property bool browserLoading: false
  property string browserError: ""

  function elide(value) {
    return Model.sanitizeString(value, 256)
  }

  function start() {
    if (_started) return
    _started = true

    // Load state from secure state helper
    stateReadProcess.command = [helperPath, "state-read"]
    stateReadProcess.running = true
    stateReadWatchdog.restart()

    // Query integration status
    checkLauncherStatus()

    // Start theme discovery
    refresh(true)
  }

  onManifestChanged: startupTimer.restart()
  Component.onCompleted: startupTimer.restart()

  Timer { id: startupTimer; interval: 25; repeat: false; onTriggered: root.start() }

  // Automatic first-run presentation timer (triggers only if setup is required)
  Timer {
    id: firstRunTimer
    interval: 200
    repeat: false
    onTriggered: {
      if (root.setupRequired) {
        var pluginId = manifest && manifest.id ? String(manifest.id) : "sanjyay.cursor-theme-manager"
        if (root.shell && typeof root.shell.summon === "function") {
          root.shell.summon(pluginId, "{}")
        }
      }
    }
  }

  function refresh(force) {
    if (!_started) return
    if (scanning || discoverProcess.running) {
      if (force) _pendingDiscoveryRefresh = true
      return
    }
    if (!force && lastScanMs > 0 && Date.now() - lastScanMs < 30000) return
    _pendingDiscoveryRefresh = false
    scanning = true
    _discoverOutput = ""
    _discoverError = ""
    discoverProcess.command = [helperPath, "discover"]
    discoverProcess.running = true
    discoverWatchdog.restart()
  }

  function refreshIfStale() { refresh(false) }

  function parseDiscovery(raw) {
    try {
      var parsed = JSON.parse(String(raw || ""))
      var normalized = Model.normalizeThemes(parsed.themes)
      themes = normalized
      themeModelVersion++
      lastScanMs = Date.now()
      _scanLoaded = true
      lastError = ""
      themesChangedByScan()

      // Populate runtimeThemeCache for any newly discovered themes
      for (var i = 0; i < normalized.length; i++) {
        var t = normalized[i]
        if (t && t.runtimeTheme && t.runtimePrepared) {
          runtimeThemeCache[t.id] = { name: t.runtimeTheme, prepared: true }
        }
      }

      if (!ready) {
        initialize(parsed.currentXcursor || "")
      } else if (_pendingSelectionThemeId) {
        // Select and apply the newly imported/renamed theme from the authoritative refreshed model
        var foundTheme = null
        for (var j = 0; j < themes.length; j++) {
          if (themes[j].id === _pendingSelectionThemeId || themes[j].displayName === _pendingSelectionThemeId) {
            foundTheme = themes[j]
            break
          }
        }
        _pendingSelectionThemeId = ""
        if (foundTheme) {
          commitTheme(foundTheme)
        }
      } else if (committedTheme) {
        // Reconcile committedTheme reference to authoritative object in refreshed themes
        for (var k = 0; k < themes.length; k++) {
          if (Model.themeEquals(themes[k], committedTheme)) {
            committedTheme = themes[k]
            break
          }
        }
        fetchRoles(committedTheme.displayName || committedTheme.id, committedTheme.path || "")
      }
      prefetchAllRoles()
    } catch (error) {
      lastError = "Cursor discovery returned invalid data"
      console.warn("sanjyay.cursor-theme-manager: discovery parse failed:", error)
    }
  }

  property var rolesCache: ({})
  property string _activeFetchingTheme: ""
  property string _pendingFetchTheme: ""
  property string _pendingFetchPath: ""

  function prefetchAllRoles() {
    if (prefetchRolesProcess.running) return
    prefetchRolesProcess.command = [helperPath, "get-all-preview-roles"]
    prefetchRolesProcess.running = true
    prefetchRolesWatchdog.restart()
  }

  function fetchRoles(themeIdentifier, themePath) {
    if (!themeIdentifier) return
    var key = Model.sanitizeString(themeIdentifier, 256)
    if (rolesCache[key]) {
      currentRoles = rolesCache[key]
      return
    }
    if (rolesCache[key.toLowerCase()]) {
      currentRoles = rolesCache[key.toLowerCase()]
      return
    }
    if (fetchRolesProcess.running) {
      _pendingFetchTheme = key
      _pendingFetchPath = themePath ? String(themePath) : ""
      return
    }
    _activeFetchingTheme = key
    var args = [helperPath, "get-preview-roles", "--theme", key]
    if (themePath) {
      args.push("--path", String(themePath))
    }
    fetchRolesProcess.command = args
    fetchRolesProcess.running = true
    fetchRolesWatchdog.restart()
  }

  function initialize(currentXcursor) {
    if (ready || !_stateLoaded || !_scanLoaded) return

    committedSize = Model.validSize(_loadedState.size)
    requestedSize = committedSize
    liveAppliedSize = committedSize
    _persistedSize = committedSize
    importedThemes = _loadedState.importedThemes || []
    integrationEnabled = Boolean(_loadedState.integrationEnabled || _loadedState.launcherAdded)
    integrationPromptSeen = integrationEnabled || setupDismissedThisSession

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

    if (_loadedState.cursorModifiedByCtm && committedTheme) {
      enqueueApply(committedTheme, committedSize, "restore")
      fetchRoles(committedTheme.displayName || committedTheme.id, committedTheme.path || "")
    } else if (committedTheme) {
      fetchRoles(committedTheme.displayName || committedTheme.id, committedTheme.path || "")
    }

    if (!launcherPromptSeen) {
      firstRunTimer.restart()
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

    _themeRequestGeneration++
    var gen = _themeRequestGeneration

    // 1. Synchronously update UI selection immediately (0 ms latency)
    committedTheme = theme
    statusText = (theme.displayName || theme.id) + " · " + committedSize + " px"

    // 2. Ensure baseline is durably captured on first-ever CTM apply
    if (root._loadedState && !root._loadedState.cursorModifiedByCtm) {
      root._loadedState.cursorModifiedByCtm = true
      baselineCaptureProcess.command = [helperPath, "capture-baseline"]
      baselineCaptureProcess.running = true
    }

    // 3. Resolve runtime identity
    var resolved = resolveRuntimeTheme(theme)
    if (resolved.prepared) {
      // FAST PATH: Direct hyprctl setcursor (~10-15 ms)
      startLiveThemeSetcursor(resolved.name, committedSize, gen, theme)
    } else {
      // PREPARE PATH: Convert XCursor to Hyprcursor in background
      statusText = "Preparing " + (theme.displayName || theme.id) + "…"
      _preparingTheme = theme
      _preparingGeneration = gen
      prepareThemeProcess.command = [
        helperPath, "ensure-hyprcursor",
        "--xcursor", theme.id,
        "--theme-path", theme.path || ""
      ]
      prepareThemeProcess.running = true
      prepareThemeWatchdog.restart()
    }

    // Fetch / load preview roles in background (never blocks live setcursor)
    if (theme.displayName || theme.id) {
      fetchRoles(theme.displayName || theme.id, theme.path || "")
    }
  }

  function resolveRuntimeTheme(theme) {
    if (!theme) return { name: "Adwaita", prepared: true }
    var id = theme.id || ""
    if (runtimeThemeCache[id]) {
      return runtimeThemeCache[id]
    }

    if (theme.runtimeTheme && theme.runtimePrepared) {
      var entry1 = { name: theme.runtimeTheme, prepared: true }
      runtimeThemeCache[id] = entry1
      return entry1
    }

    if (theme.hyprcursor && theme.hyprcursor !== "-") {
      var entry2 = { name: theme.hyprcursor, prepared: true }
      runtimeThemeCache[id] = entry2
      return entry2
    }

    if (theme.formats && theme.formats.indexOf("hyprcursor") >= 0 && theme.xcursor) {
      var entry3 = { name: theme.xcursor, prepared: true }
      runtimeThemeCache[id] = entry3
      return entry3
    }

    return { name: theme.xcursor || id, prepared: false }
  }

  function startLiveThemeSetcursor(runtimeThemeName, size, generation, themeObj) {
    _activeThemeGeneration = generation
    liveThemeProcess.command = ["hyprctl", "setcursor", runtimeThemeName, String(size)]
    liveThemeProcess.running = true
    liveThemeWatchdog.restart()
  }

  function flushFinalThemePersistence() {
    if (!committedTheme) return
    var doc = JSON.stringify(committedTheme)
    var sz = committedSize

    persistThemeProcess.command = [
      helperPath, "persist-theme",
      "--theme", doc,
      "--size", String(sz)
    ]
    persistThemeProcess.running = true
    persistThemeWatchdog.restart()
  }

  function commitSize(size) {
    previewTimer.stop()
    _debouncedPreview = null
    var target = Model.validSize(size)
    if (target === requestedSize && !liveSetcursorProcess.running && !trailingLiveSizeTimer.running && !commitSizeDebounceTimer.running && target === _persistedSize) return

    // 1. Synchronous Instant UI Update (0 ms latency, no subprocess)
    _sizeRequestGeneration++
    requestedSize = target
    committedSize = target
    if (root._loadedState) root._loadedState.cursorModifiedByCtm = true
    statusText = (committedTheme ? (committedTheme.displayName || committedTheme.id) : "Cursor") + " · " + requestedSize + " px"

    // 2. Trailing-edge ONLY live apply: restart debounce timer on every input click
    trailingLiveSizeTimer.restart()
  }

  function dispatchTrailingLiveSize() {
    if (!committedTheme) return
    var target = requestedSize
    var gen = _sizeRequestGeneration

    if (liveSetcursorProcess.running) {
      return
    }

    startLiveSetcursor(target, gen)
  }

  function startLiveSetcursor(size, generation) {
    if (!committedTheme) return
    _activeLiveGeneration = generation

    var resolvedTheme = committedTheme.hyprcursor || committedTheme.xcursor || committedTheme.id || "Adwaita"
    if (resolvedTheme === "-") {
      resolvedTheme = committedTheme.xcursor || committedTheme.id || "Adwaita"
    }

    liveSetcursorProcess.command = ["hyprctl", "setcursor", resolvedTheme, String(size)]
    liveSetcursorProcess.running = true
    liveSetcursorWatchdog.restart()
  }

  function flushFinalSizePersistence() {
    if (!committedTheme) return
    var finalGen = _sizeRequestGeneration
    var finalSize = requestedSize
    _persistedSize = finalSize

    var hypr = committedTheme.hyprcursor || "-"
    var xcur = committedTheme.xcursor || "-"

    persistSizeProcess.command = [
      helperPath, "persist-size",
      "--hyprcursor", hypr,
      "--xcursor", xcur,
      "--size", String(finalSize)
    ]
    persistSizeProcess.running = true
    persistSizeWatchdog.restart()
  }

  function enqueueApply(theme, size, kind, generation) {
    if (!theme) return
    var gen = generation !== undefined ? generation : (++_sizeRequestGeneration)
    _queuedApply = { theme: theme, size: Model.validSize(size), kind: kind, generation: gen }
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
    applyWatchdog.restart()
  }

  function persistState() {
    var doc = Model.stateDocument(
      committedTheme,
      committedSize,
      importedThemes,
      integrationPromptSeen,
      integrationEnabled,
      _loadedState.cursorModifiedByCtm,
      _loadedState.preCtmCursor || _loadedState.originalCursor
    )
    stateWriteProcess.command = [helperPath, "state-write", "--state", doc]
    stateWriteProcess.running = true
    stateWriteWatchdog.restart()
  }

  function indexOfCommitted() {
    if (!committedTheme) return -1
    for (var i = 0; i < themes.length; i++) {
      if (Model.themeEquals(themes[i], committedTheme)) return i
    }
    return -1
  }

  function restoreConfigured() {
    if (committedTheme) enqueueApply(committedTheme, committedSize, "restore")
  }

  // ===========================================================================
  // Integration & Removal Watcher API
  // ===========================================================================

  function checkIntegrationStatus() {
    if (integrationStatusProcess.running) return
    integrationStatusProcess.command = [helperPath, "integration-status"]
    integrationStatusProcess.running = true
    integrationStatusWatchdog.restart()
  }
  function checkLauncherStatus() { checkIntegrationStatus() }

  function enableIntegration() {
    if (integrationEnableProcess.running || integrationDisableProcess.running) return
    integrationLoading = true
    integrationError = ""
    integrationEnableProcess.command = [helperPath, "integration-enable"]
    integrationEnableProcess.running = true
    integrationEnableWatchdog.restart()
  }
  function addLauncher() { enableIntegration() }

  function disableIntegration() {
    if (integrationEnableProcess.running || integrationDisableProcess.running) return
    integrationLoading = true
    integrationError = ""
    integrationDisableProcess.command = [helperPath, "integration-disable"]
    integrationDisableProcess.running = true
    integrationDisableWatchdog.restart()
  }
  function removeLauncher() { disableIntegration() }

  function dismissIntegrationPrompt() {
    setupDismissedThisSession = true
    integrationPromptSeen = true
    integrationChanged()
    launcherChanged()
  }
  function dismissLauncherPrompt() { dismissIntegrationPrompt() }

  // ===========================================================================
  // File Chooser, Browser, Import API
  // ===========================================================================

  function chooseAndImportFile() {
    if (chooseFileProcess.running || importProcess.running) return
    chooseFileProcess.running = true
    chooseFileWatchdog.restart()
  }

  function importTheme(sourcePath, optionalName) {
    if (!sourcePath || importProcess.running) return
    lastError = ""
    statusText = "Importing theme…"
    var args = [helperPath, "import", "--source", String(sourcePath)]
    if (optionalName) {
      args.push("--name", Model.sanitizeString(optionalName, 100))
    }
    importProcess.command = args
    importProcess.running = true
    importWatchdog.restart()
  }

  function removeImportedTheme(theme) {
    if (!theme || !theme.id || removeImportProcess.running) return
    if (!theme.imported && theme.sourceType !== "imported") return
    lastError = ""
    if (committedTheme && (committedTheme.id === theme.id || committedTheme.displayName === theme.displayName)) {
      var fb = Model.fallbackTheme(themes, "Banana")
      if (fb) enqueueApply(fb, committedSize, "commit")
    }
    rolesCache = ({})
    removeImportProcess.command = [helperPath, "remove-imported", "--id", String(theme.id)]
    removeImportProcess.running = true
    removeImportWatchdog.restart()
  }

  function openThemeFolder(theme) {
    if (!theme || !theme.path || openFolderProcess.running) return
    openFolderProcess.command = [helperPath, "open-folder", "--path", String(theme.path)]
    openFolderProcess.running = true
    openFolderWatchdog.restart()
  }

  function renameImportedTheme(theme, newName) {
    if (!theme || !theme.id || !newName || renameImportProcess.running) return
    lastError = ""
    rolesCache = ({})
    renameImportProcess.command = [helperPath, "rename-imported", "--id", String(theme.id), "--name", Model.sanitizeString(newName, 100)]
    renameImportProcess.running = true
    renameImportWatchdog.restart()
  }

  function browseDirectory(path) {
    if (listDirProcess.running) return
    browserLoading = true
    browserError = ""
    var target = path ? String(path) : (browserPath || "")
    listDirProcess.command = [helperPath, "list-dir", "--path", target]
    listDirProcess.running = true
    listDirWatchdog.restart()
  }

  // ===========================================================================
  // PROCESS DEFINITIONS WITH WATCHDOG TIMERS
  // ===========================================================================

  // 1. State Read Process
  Timer {
    id: stateReadWatchdog
    interval: 6000
    repeat: false
    onTriggered: {
      if (stateReadProcess.running) {
        stateReadProcess.running = false
        root._loadedState = Model.parseState("")
        root._stateLoaded = true
        root.initialize("")
      }
    }
  }

  Process {
    id: stateReadProcess
    running: false
    command: []
    stdout: StdioCollector { id: stateReadStdout; waitForEnd: true }
    onExited: function(exitCode) {
      stateReadWatchdog.stop()
      var text = exitCode === 0 ? (stateReadStdout.text || "") : ""
      root._loadedState = Model.parseState(text)
      root._stateLoaded = true
      root.initialize("")
    }
  }

  // 2. State Write Process
  Timer {
    id: stateWriteWatchdog
    interval: 6000
    repeat: false
    onTriggered: if (stateWriteProcess.running) stateWriteProcess.running = false
  }

  Process {
    id: stateWriteProcess
    running: false
    command: []
    onExited: function(exitCode) {
      stateWriteWatchdog.stop()
    }
  }

  // 3. Integration Status Process
  Timer {
    id: integrationStatusWatchdog
    interval: 8000
    repeat: false
    onTriggered: if (integrationStatusProcess.running) integrationStatusProcess.running = false
  }

  Process {
    id: integrationStatusProcess
    running: false
    command: []
    stdout: StdioCollector { id: integrationStatusStdout; waitForEnd: true }
    onExited: function(exitCode) {
      integrationStatusWatchdog.stop()
      if (exitCode === 0) {
        try {
          var res = JSON.parse(integrationStatusStdout.text || "{}")
          if (res.ok) {
            root.integrationEnabled = Boolean(res.enabled)
            root.integrationPromptSeen = root.integrationEnabled || root.setupDismissedThisSession
            root.integrationArtifacts = res.artifacts || ({})
            if (res.paths && res.paths.desktop) root.launcherPath = res.paths.desktop
            root.integrationChanged()
            root.launcherChanged()
          }
        } catch (e) {}
      }
    }
  }

  // 4. Integration Enable Process
  Timer {
    id: integrationEnableWatchdog
    interval: 12000
    repeat: false
    onTriggered: {
      if (integrationEnableProcess.running) {
        integrationEnableProcess.running = false
        root.integrationLoading = false
        root.integrationError = "Enabling integration timed out"
      }
    }
  }

  Process {
    id: integrationEnableProcess
    running: false
    command: []
    stdout: StdioCollector { id: integrationEnableStdout; waitForEnd: true }
    stderr: StdioCollector { id: integrationEnableStderr; waitForEnd: true }
    onExited: function(exitCode) {
      integrationEnableWatchdog.stop()
      root.integrationLoading = false
      if (exitCode === 0) {
        root.integrationEnabled = true
        root.integrationPromptSeen = true
        root.integrationError = ""
        root.checkIntegrationStatus()
      } else {
        var err = "Failed to enable integration"
        try {
          var p = JSON.parse(integrationEnableStdout.text || "{}")
          if (p.error) err = p.error
        } catch (e) {
          if (integrationEnableStderr.text) err = root.elide(integrationEnableStderr.text)
        }
        root.integrationError = err
      }
      root.integrationChanged()
      root.launcherChanged()
    }
  }

  // 5. Integration Disable Process
  Timer {
    id: integrationDisableWatchdog
    interval: 12000
    repeat: false
    onTriggered: {
      if (integrationDisableProcess.running) {
        integrationDisableProcess.running = false
        root.integrationLoading = false
        root.integrationError = "Disabling integration timed out"
      }
    }
  }

  Process {
    id: integrationDisableProcess
    running: false
    command: []
    stdout: StdioCollector { id: integrationDisableStdout; waitForEnd: true }
    stderr: StdioCollector { id: integrationDisableStderr; waitForEnd: true }
    onExited: function(exitCode) {
      integrationDisableWatchdog.stop()
      root.integrationLoading = false
      if (exitCode === 0) {
        root.integrationEnabled = false
        root.integrationError = ""
        root.checkIntegrationStatus()
      } else {
        root.integrationError = root.elide(integrationDisableStderr.text || "Failed to disable integration")
      }
      root.integrationChanged()
      root.launcherChanged()
    }
  }

  // 5b. Integration Dismiss Process
  Process {
    id: integrationDismissProcess
    running: false
    command: []
  }

  // 6. Discovery Process
  Timer {
    id: discoverWatchdog
    interval: 12000
    repeat: false
    onTriggered: {
      if (discoverProcess.running) {
        discoverProcess.running = false
        root.scanning = false
        root.lastError = "Cursor discovery timed out"
      }
    }
  }

  Process {
    id: discoverProcess
    running: false
    command: []
    stdout: StdioCollector { id: discoverStdout; waitForEnd: true; onStreamFinished: root._discoverOutput = text }
    stderr: StdioCollector { id: discoverStderr; waitForEnd: true; onStreamFinished: root._discoverError = text }
    onExited: function(exitCode) {
      discoverWatchdog.stop()
      root.scanning = false
      if (exitCode === 0) {
        root.parseDiscovery(discoverStdout.text || root._discoverOutput)
      } else {
        root.lastError = root.elide(discoverStderr.text || root._discoverError || "Cursor discovery failed")
        console.warn("sanjyay.cursor-theme-manager:", root.lastError)
      }

      if (root._pendingDiscoveryRefresh) {
        root._pendingDiscoveryRefresh = false
        Qt.callLater(function() { root.refresh(true) })
      }
    }
  }

  // 7. Fetch Roles Process
  Timer {
    id: fetchRolesWatchdog
    interval: 7000
    repeat: false
    onTriggered: if (fetchRolesProcess.running) fetchRolesProcess.running = false
  }

  Process {
    id: fetchRolesProcess
    running: false
    command: []
    stdout: StdioCollector { id: fetchRolesStdout; waitForEnd: true }
    onExited: function(exitCode) {
      fetchRolesWatchdog.stop()
      var fetchingTheme = root._activeFetchingTheme
      root._activeFetchingTheme = ""
      if (exitCode === 0) {
        try {
          var res = JSON.parse(fetchRolesStdout.text || "{}")
          if (res && typeof res === "object") {
            if (fetchingTheme) {
              root.rolesCache[fetchingTheme] = res
            }
            root.currentRoles = res
          }
        } catch (e) {
          console.warn("sanjyay.cursor-theme-manager: failed to parse preview roles output:", e)
        }
      }
      if (root._pendingFetchTheme) {
        var nextTheme = root._pendingFetchTheme
        var nextPath = root._pendingFetchPath
        root._pendingFetchTheme = ""
        root._pendingFetchPath = ""
        root.fetchRoles(nextTheme, nextPath)
      }
    }
  }

  // 8. Prefetch Roles Process
  Timer {
    id: prefetchRolesWatchdog
    interval: 18000
    repeat: false
    onTriggered: if (prefetchRolesProcess.running) prefetchRolesProcess.running = false
  }

  Process {
    id: prefetchRolesProcess
    running: false
    command: []
    stdout: StdioCollector { id: prefetchRolesStdout; waitForEnd: true }
    onExited: function(exitCode) {
      prefetchRolesWatchdog.stop()
      if (exitCode === 0) {
        try {
          var allRes = JSON.parse(prefetchRolesStdout.text || "{}")
          if (allRes && typeof allRes === "object") {
            for (var k in allRes) {
              root.rolesCache[k] = allRes[k]
            }
            if (root.committedTheme) {
              var cName = root.committedTheme.displayName || root.committedTheme.id
              if (root.rolesCache[cName]) {
                root.currentRoles = root.rolesCache[cName]
              }
            }
          }
        } catch (e) {
          console.warn("sanjyay.cursor-theme-manager: prefetch parse failed:", e)
        }
      }
    }
  }

  // 9. List Directory Process
  Timer {
    id: listDirWatchdog
    interval: 6000
    repeat: false
    onTriggered: {
      if (listDirProcess.running) {
        listDirProcess.running = false
        root.browserLoading = false
        root.browserError = "Directory reading timed out"
      }
    }
  }

  Process {
    id: listDirProcess
    running: false
    command: []
    stdout: StdioCollector { id: listDirStdout; waitForEnd: true }
    stderr: StdioCollector { id: listDirStderr; waitForEnd: true }
    onExited: function(exitCode) {
      listDirWatchdog.stop()
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

  // 10. Choose File Process
  Timer {
    id: chooseFileWatchdog
    interval: 60000
    repeat: false
    onTriggered: if (chooseFileProcess.running) chooseFileProcess.running = false
  }

  Process {
    id: chooseFileProcess
    running: false
    command: [root.helperPath, "choose-file"]
    stdout: StdioCollector { id: chooseFileStdout; waitForEnd: true }
    onExited: function(exitCode) {
      chooseFileWatchdog.stop()
      var selected = String(chooseFileStdout.text || "").trim()
      if (exitCode === 0 && selected.length > 0) {
        root.importTheme(selected)
      }
    }
  }

  // 11. Import Process
  Timer {
    id: importWatchdog
    interval: 130000
    repeat: false
    onTriggered: {
      if (importProcess.running) {
        importProcess.running = false
        root.lastError = "Import operation timed out"
        root.statusText = "Import failed"
        root.importFailed("Import operation timed out")
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
      importWatchdog.stop()
      var raw = String(importStdout.text || "").trim()
      try {
        var parsed = JSON.parse(raw)
        if (parsed.ok && parsed.theme) {
          var msg = parsed.alreadyImported ? "Already imported: " + parsed.theme.displayName : "Successfully imported " + parsed.theme.displayName
          root.statusText = msg
          root.lastError = ""

          // Register runtime cache mapping if available from import
          if (parsed.theme.hyprcursor) {
            root.runtimeThemeCache[parsed.theme.id] = { name: parsed.theme.hyprcursor, prepared: true }
          }

          // Set pending selection so that discovery selects and applies the authoritative theme from the model
          root._pendingSelectionThemeId = parsed.theme.id || parsed.theme.displayName
          root.refresh(true)
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

  // 12. Remove Import Process
  Timer {
    id: removeImportWatchdog
    interval: 12000
    repeat: false
    onTriggered: if (removeImportProcess.running) removeImportProcess.running = false
  }

  Process {
    id: removeImportProcess
    running: false
    command: []
    onExited: function(exitCode) {
      removeImportWatchdog.stop()
      if (exitCode === 0) {
        root.statusText = "Imported theme removed"
        root.refresh(true)
      } else {
        root.lastError = "Could not remove imported theme"
      }
    }
  }

  // 13. Rename Import Process
  Timer {
    id: renameImportWatchdog
    interval: 12000
    repeat: false
    onTriggered: if (renameImportProcess.running) renameImportProcess.running = false
  }

  Process {
    id: renameImportProcess
    running: false
    command: []
    stdout: StdioCollector { id: renameImportStdout; waitForEnd: true }
    stderr: StdioCollector { id: renameImportStderr; waitForEnd: true }
    onExited: function(exitCode) {
      renameImportWatchdog.stop()
      if (exitCode === 0) {
        root.rolesCache = ({})
        root.statusText = "Theme renamed"
        root.refresh(true)
      } else {
        root.lastError = root.elide(renameImportStderr.text || "Failed to rename theme")
      }
    }
  }

  // 14. Open Folder Process
  Timer {
    id: openFolderWatchdog
    interval: 6000
    repeat: false
    onTriggered: if (openFolderProcess.running) openFolderProcess.running = false
  }

  Process {
    id: openFolderProcess
    running: false
    command: []
    onExited: function(exitCode) {
      openFolderWatchdog.stop()
    }
  }

  // 15. Apply Process
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

  // 10. Trailing-Edge Direct Live Setcursor Process (Exactly one reload per burst)
  Timer {
    id: liveSetcursorWatchdog
    interval: 1500
    repeat: false
    onTriggered: {
      if (liveSetcursorProcess.running) {
        liveSetcursorProcess.running = false
        root._activeLiveGeneration = 0
        if (root._sizeRequestGeneration > root._activeLiveGeneration) {
          trailingLiveSizeTimer.restart()
        }
      }
    }
  }

  Process {
    id: liveSetcursorProcess
    running: false
    command: []
    onExited: function(exitCode) {
      liveSetcursorWatchdog.stop()
      var completedGen = root._activeLiveGeneration
      root._activeLiveGeneration = 0

      if (exitCode === 0 && completedGen >= root._sizeRequestGeneration) {
        root.liveAppliedSize = root.requestedSize
        root.commitSizeDebounceTimer.restart()
      }

      // If user clicked again while setcursor was in flight
      if (root._sizeRequestGeneration > completedGen) {
        trailingLiveSizeTimer.restart()
      }
    }
  }

  // 10b. Dedicated Silent Size Persistence Process (Zero setcursor calls)
  Timer {
    id: persistSizeWatchdog
    interval: 5000
    repeat: false
    onTriggered: if (persistSizeProcess.running) persistSizeProcess.running = false
  }

  Process {
    id: persistSizeProcess
    running: false
    command: []
    onExited: function(exitCode) {
      persistSizeWatchdog.stop()
    }
  }

  // 10c. Fast Baseline Capture Process (First-Ever Apply Only)
  Timer {
    id: baselineCaptureWatchdog
    interval: 3000
    repeat: false
    onTriggered: if (baselineCaptureProcess.running) baselineCaptureProcess.running = false
  }

  Process {
    id: baselineCaptureProcess
    running: false
    command: []
    onExited: function(exitCode) {
      baselineCaptureWatchdog.stop()
    }
  }

  // 10d. Background Theme Preparation Process (XCursor -> Hyprcursor)
  Timer {
    id: prepareThemeWatchdog
    interval: 12000
    repeat: false
    onTriggered: {
      if (prepareThemeProcess.running) {
        prepareThemeProcess.running = false
        root._preparingTheme = null
        root._preparingGeneration = 0
      }
    }
  }

  Process {
    id: prepareThemeProcess
    running: false
    command: []
    stdout: StdioCollector { id: prepareThemeStdout; waitForEnd: true }
    onExited: function(exitCode) {
      prepareThemeWatchdog.stop()
      var prepTheme = root._preparingTheme
      var prepGen = root._preparingGeneration
      root._preparingTheme = null
      root._preparingGeneration = 0

      if (exitCode === 0 && prepTheme) {
        var runtimeName = String(prepareThemeStdout.text || "").trim()
        if (runtimeName) {
          prepTheme.hyprcursor = runtimeName
          prepTheme.runtimeTheme = runtimeName
          prepTheme.runtimePrepared = true
          root.runtimeThemeCache[prepTheme.id] = { name: runtimeName, prepared: true }

          if (prepGen >= root._themeRequestGeneration && root.committedTheme && root.committedTheme.id === prepTheme.id) {
            root.statusText = (prepTheme.displayName || prepTheme.id) + " · " + root.committedSize + " px"
            root.startLiveThemeSetcursor(runtimeName, root.committedSize, prepGen, prepTheme)
          }
        }
      }
    }
  }

  // 10e. Fast-Path Live Theme Setcursor Process
  Timer {
    id: liveThemeWatchdog
    interval: 1500
    repeat: false
    onTriggered: if (liveThemeProcess.running) liveThemeProcess.running = false
  }

  Process {
    id: liveThemeProcess
    running: false
    command: []
    onExited: function(exitCode) {
      liveThemeWatchdog.stop()
      var completedGen = root._activeThemeGeneration
      root._activeThemeGeneration = 0

      if (exitCode === 0 && completedGen >= root._themeRequestGeneration) {
        root.liveAppliedTheme = root.committedTheme
        root.persistThemeDebounceTimer.restart()
      }
    }
  }

  // 10f. Dedicated Silent Theme Persistence Process (Zero setcursor calls)
  Timer {
    id: persistThemeWatchdog
    interval: 5000
    repeat: false
    onTriggered: if (persistThemeProcess.running) persistThemeProcess.running = false
  }

  Process {
    id: persistThemeProcess
    running: false
    command: []
    onExited: function(exitCode) {
      persistThemeWatchdog.stop()
    }
  }

  // 11. Full Persistent Apply Process
  Timer {
    id: applyWatchdog
    interval: 12000
    repeat: false
    onTriggered: {
      if (applyProcess.running) {
        applyProcess.running = false
        root.applying = false
        root.lastError = "Cursor apply operation timed out"
        root._activeApply = null
        root.startQueuedApply()
      }
    }
  }

  Process {
    id: applyProcess
    running: false
    command: []
    stdout: StdioCollector { id: applyStdout; waitForEnd: true; onStreamFinished: root._applyStdout = text }
    stderr: StdioCollector { id: applyStderr; waitForEnd: true; onStreamFinished: root._applyStderr = text }
    onExited: function(exitCode) {
      applyWatchdog.stop()
      var request = root._activeApply
      root.applying = false
      var reqGen = request ? (request.generation || 0) : 0

      if (exitCode !== 0) {
        if (reqGen >= root._sizeRequestGeneration) {
          root.lastError = root.elide(applyStderr.text || root._applyStderr || applyStdout.text || root._applyStdout || "Cursor could not be applied")
          console.warn("sanjyay.cursor-theme-manager:", root.lastError)
          if (request && request.kind === "commit") {
            root.statusText = "Failed to switch to " + (request.theme ? (request.theme.displayName || request.theme.id) : "theme")
          } else if (request && request.kind === "preview") {
            root.previewTheme = null
            root.previewSize = 0
            root.statusText = "Preview unavailable for " + (request.theme ? (request.theme.displayName || request.theme.id) : "theme")
          }
        }
      } else if (request) {
        if (reqGen >= root._sizeRequestGeneration) {
          root.lastError = ""
          if (request.kind === "preview") {
            root.previewTheme = request.theme
            root.previewSize = request.size
            root.statusText = "Previewing " + (request.theme.displayName || request.theme.id)
          } else if (request.kind === "commit") {
            root.committedTheme = request.theme
            root.committedSize = request.size
            root.previewTheme = null
            root.previewSize = 0
            root.persistState()
            root.statusText = (request.theme.displayName || request.theme.id) + " · " + request.size + " px"
          } else {
            root.previewTheme = null
            root.previewSize = 0
            root.statusText = root.committedTheme ? (root.committedTheme.displayName || root.committedTheme.id) + " · " + root.committedSize + " px" : "Ready"
          }
        }
      }
      root._activeApply = null
      root.startQueuedApply()
    }
  }
}
