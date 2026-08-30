# Omarchy Cursor Switcher

A native Omarchy Quattro / `omarchy-shell` panel for discovering, previewing, applying, and persisting Linux cursor themes. It supports current Hyprcursor themes, legacy XCursor themes for GTK and other clients, discrete cursor sizes, keyboard navigation, safe hover previews, and a bundled original cursor family called **Omarchy Banana**.

![Cursor Switcher panel](docs/panel.png)

## Features

- Discovers real cursor themes in `~/.local/share/icons`, `~/.icons`, and the `XDG_DATA_DIRS` icon roots (normally `/usr/share/icons`).
- Distinguishes Hyprcursor, XCursor, and combined packages instead of listing ordinary icon themes.
- Uses `hyprctl setcursor` for live Hyprcursor changes and `gsettings` for GTK/XCursor compatibility.
- Updates the systemd/D-Bus activation environment and Quattro's live Hyprland Lua environment for newly launched applications.
- Persists the selection in `~/.config/omarchy/cursor-switcher.json` and UWSM-owned environment fragments.
- Debounces live previews and restores the committed cursor when hover ends, the panel closes, or Escape is pressed.
- Installs the bundled theme idempotently at `~/.local/share/icons/Omarchy-Banana` without sudo.
- Has no polling loop and does not scan cursor directories continuously.

## Install

This repository is already usable as a local plugin. From its root:

```bash
ln -s "$PWD" ~/.config/omarchy/plugins/goblin.cursor-switcher
omarchy-shell shell rescanPlugins
omarchy plugin enable goblin.cursor-switcher
```

For a normal published Git checkout, Omarchy's standard `omarchy plugin add <git-url> --enable` flow may be used instead. No install hook or sudo command is required. The service installs/updates the bundled cursor package on first load.

Open or toggle the selector:

```bash
omarchy-shell shell toggle goblin.cursor-switcher '{}'
```

A Hyprland shortcut can run that exact command. The panel also supports `summon` and `hide`:

```bash
omarchy-shell shell summon goblin.cursor-switcher '{}'
omarchy-shell shell hide goblin.cursor-switcher
```

Arrow keys (or `h/j/k/l`) navigate, Tab switches between the theme grid and size row, Enter/Space commits, `r` refreshes, and Escape cancels any preview and closes the panel.

## Applying Omarchy Banana manually

Through the loaded plugin service:

```bash
omarchy-shell shell call goblin.cursor-switcher applyTheme '{"theme":"Omarchy-Banana","size":24}'
```

Or directly through the self-contained backend:

```bash
~/.config/omarchy/plugins/goblin.cursor-switcher/scripts/cursorctl apply \
  --hyprcursor Omarchy-Banana --xcursor Omarchy-Banana --size 24 --commit
```

The plugin-owned IPC methods are `status`, `refresh`, `restore`, `applyTheme`, `preview`, and `cancelPreview` in addition to the shell's normal summon/hide/toggle lifecycle.

## Hyprcursor and XCursor behavior

Hyprland 0.37 and newer accepts only Hyprcursor packages through `hyprctl setcursor`. GTK and some other clients still use XCursor. For a combined package such as Omarchy Banana, the plugin applies both paths.

An XCursor-only theme can be committed for GTK, future applications, and the next login, but it cannot replace an already-active Hyprcursor in the current compositor. The panel reports this instead of claiming a full live switch. Live preview is enabled only when both the target and the committed cursor have a reversible Hyprcursor path.

Many applications cache their cursor theme. New applications inherit the updated session environment; existing GTK, Qt, Chromium, or Electron processes may need to be restarted. The plugin writes:

- `~/.config/uwsm/env.d/90-omarchy-cursor-switcher`
- `~/.config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher`

UWSM sources these fragments at the next graphical login. It also updates the current systemd/D-Bus activation environment and the Quattro Lua environment immediately.

## Omarchy Banana

![Omarchy Banana cursor roles](docs/banana-preview.png)

Omarchy Banana contains 30 canonical roles and the common Linux aliases: default, link pointer, text and vertical text, crosshair, cell, grab/grabbing, move, wait, progress, prohibited, copy, alias, help, context menu, zoom controls, all cardinal/diagonal resize directions, and paired resize axes.

![Normal intact banana changing to its clickable peeled role](docs/banana-intact-to-peeled.png)

The default pointer is a chunky intact banana and uses its narrow upper-left stem tip as the click point. Its packaged 24 px hotspot is `(3, 2)`. Applications naturally request another cursor role over clickable controls; `pointer`, `link`, `hand`, `hand1`, `hand2`, `pointing_hand`, and the two standard installed XCursor hand hashes all resolve to the original peeled-banana artwork. That role's hotspot is the top of the exposed fruit—`(12, 2)` at 24 px. The intact/peeled change is native role switching: it uses no polling, timer, animation, mouse hook, or application integration.

Directional and text cursors prioritize familiar silhouettes over the fruit motif. Resize, move, crosshair, drag, and action badges share the same heavier outline and optical weight as the redesigned default.

**Clean-room statement:** Omarchy Banana is original artwork authored from scratch for this project. It contains no artwork, geometry, colors, animation, source structure, code, or generated cursor assets from third-party banana cursor projects, and it has no runtime or build-time dependency on them.

## Building the assets

Prebuilt Hyprcursor and XCursor output ships in `themes/omarchy-banana/generated/Omarchy-Banana`, so runtime selection needs no Python, Node, renderer, or compiler.

Contributor build dependencies (Arch package names) are:

```text
python gcc pkgconf librsvg hyprcursor libxcursor libpng xcur2png
```

Rebuild deterministically with:

```bash
./scripts/build-banana-theme
```

The pipeline first regenerates the canonical 64×64 SVGs from the shared clean-room design system in `themes/omarchy-banana/generate-svg-sources.py`. It rasterizes 16, 20, 24, 28, 32, 40, 48, and 64 px XCursor frames, writes them through the installed `libXcursor` API, and builds vector Hyprcursor archives with the official `hyprcursor-util`. Common role names are symlinked/overridden instead of duplicating artwork.

## Architecture

- `Panel.qml` owns only panel lifecycle, focus/navigation, and presentation.
- `CursorService.qml` owns discovery cadence, state, preview/restore transitions, process orchestration, installation, errors, and persistence.
- `CursorModel.js` contains deterministic normalization, deduplication, state parsing, fallback, size, command, and preview-state logic.
- `components/` contains the theme card/grid and discrete size selector.
- `scripts/cursorctl` is the validated argv-oriented runtime backend. It never executes theme-provided code.
- `themes/omarchy-banana/source/` contains canonical SVG artwork; `generated/` contains the combined installable package.

Discovery rejects unsafe theme names and paths, does not follow theme paths outside their configured root, parses only constrained metadata keys, and verifies that a cursor payload exists. The bundled installer refuses an existing unowned `Omarchy-Banana` directory and replaces only its own marked package atomically.

## Development and tests

Run everything with:

```bash
./tests/run.sh
```

Coverage includes cursor directory/format detection, normalization and deduplication, persistence round trips and corrupt input, missing-theme fallback, command argv construction, preview/cancel/commit transitions, supported sizes, installer idempotence and collision refusal, unsafe inputs, UWSM persistence, SVG/XML constraints, every generated role and alias, intact-versus-peeled role mappings, XCursor alias decoding/hotspots, direct `libhyprcursor` alias loading/hotspots, and `qmllint` against the installed Omarchy shell imports.

For an isolated native role-switching check, apply Omarchy Banana and run `qml tests/manual-cursor-roles.qml`. The test surface requests default, pointing-hand, horizontal-resize, open-hand, and text cursors directly from Qt.

## Removal

Disable/remove the plugin with Omarchy's normal command, or remove the local development symlink:

```bash
omarchy plugin disable goblin.cursor-switcher
rm ~/.config/omarchy/plugins/goblin.cursor-switcher
```

The generated cursor, saved selection, and UWSM fragments are deliberately not deleted behind the user's back. If desired, remove only these plugin-owned paths after checking them:

```text
~/.local/share/icons/Omarchy-Banana
~/.config/omarchy/cursor-switcher.json
~/.config/uwsm/env.d/90-omarchy-cursor-switcher
~/.config/uwsm/env-hyprland.d/90-omarchy-cursor-switcher
```

## Known limitations

- Existing applications may retain cached cursors until restarted.
- XCursor-only themes cannot replace a live Hyprcursor inside the current Hyprland session; the compositor updates at the next login.
- Arbitrary third-party XCursor thumbnails are intentionally represented by a restrained fallback glyph. Parsing cursor binaries solely for card artwork would add cost and fragility; the bundled Banana card uses its actual SVG.
- Wait/progress are strong static cursors in v1 rather than animated cursors.
