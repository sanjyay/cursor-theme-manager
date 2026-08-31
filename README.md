# Cursor Theme (Omarchy Plugin)

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](manifest.json)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Hyprland%20%7C%20Omarchy-purple.svg)](https://omarchyplugins.com)

A native, keyboard-first cursor theme manager and previewer for **Omarchy** and **Hyprland**. It features dynamic multi-role previews, live hover inspection, discrete size scaling, native in-app archive/folder importing with automatic XCursor-to-Hyprcursor compilation, and bundled curated open-source cursor themes.

---

## Features

- **Standalone Application:** Automatically installs a desktop entry (`Cursor Theme`) and launcher command (`omarchy-cursor-switcher`). Open and configure your cursor directly from your application launcher without needing manual keybindings.
- **Dynamic Role Previews:** Automatically extracts and renders vector/raster preview cards for semantic roles (`Default`, `Pointer`, `Text`, `Move`, `Resize`, `Wait`). If a theme does not define a role (e.g. no `Wait` cursor), the card is hidden and remaining previews automatically reflow and center.
- **Accurate Hotspot Indicators:** Hovering any preview card displays a subtle indicator (`•`) at the exact hotspot coordinate defined by the Hyprcursor/XCursor metadata.
- **Hover-to-Preview:** Browse themes in the sidebar to temporarily inspect preview cards and metadata without modifying active session settings. Clicking applies and commits the theme.
- **Synchronized Size Control:** Stepper buttons (`−` / `+`) paired with a discrete slider track supporting standard scale snap points (16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256 px).
- **In-App Native Importer:** Built-in modal file browser matching Omarchy design tokens for importing local directories or archives (`.zip`, `.tar.gz`, `.tar.xz`, etc.).
- **Automatic Hyprcursor Compilation:** Legacy XCursor themes are automatically converted to native Hyprcursor packages on-the-fly using `hyprcursor-util`.
- **Imported Theme Management:** Rename, open directory, or safely remove imported themes directly from the UI or CLI.
- **Smart Filtering & Categorization:** Automatically groups themes into `BUNDLED` and `IMPORTED` sections. A compact case-insensitive search bar appears automatically when 10 or more themes are present.
- **Persistent & Compositor-Aware:** Instantly applies changes via `hyprctl setcursor` and `gsettings`, updating UWSM environment files (`~/.config/uwsm/env.d/90-omarchy-cursor-switcher`) and D-Bus activation environments for new applications.
- **Fully Responsive:** Fluid layouts designed for full-screen, split tiled (50/50), or compact floating windows.

---

## Installation

### Via Omarchy CLI

```bash
omarchy plugin add https://github.com/sanjyay/cursor-switcher --enable
```

### Manual / Local Development

Clone or symlink the repository into your Omarchy plugins directory:

```bash
git clone https://github.com/sanjyay/cursor-switcher.git ~/.config/omarchy/plugins/sanjyay.cursor-switcher
omarchy-shell shell rescanPlugins
omarchy plugin enable sanjyay.cursor-switcher
```

---

## Launching & Configuring

Cursor Theme installs as a standard graphical application on your system:

- **Application Launcher:** Open your app launcher (Omarchy drawer, Rofi, Fuzzel, etc.) and search for **Cursor Theme** (or *Mouse*, *Pointer*, *Banana*).
- **Command Line:** Run `omarchy-cursor-switcher` from any terminal.
- **Omarchy Shell IPC:**
  ```bash
  omarchy-shell shell summon sanjyay.cursor-switcher '{}'
  omarchy-shell shell toggle sanjyay.cursor-switcher '{}'
  omarchy-shell shell hide sanjyay.cursor-switcher
  ```

---

## Keyboard Navigation

| Key | Action |
| :--- | :--- |
| **Up / Down** (`k` / `j`) | Navigate theme list |
| **Left / Right** (`h` / `l`) | Decrease / increase cursor size (when size focused) |
| **Tab / Shift+Tab** | Switch focus between theme list and size stepper |
| **Enter / Space** | Apply and commit focused theme / confirm dialog |
| **Escape** | Clear search filter, close dialogs, or close panel |
| **r** | Refresh / rescan installed cursor themes |

---

## Downloading Cursor Themes

You can import any standard Linux cursor theme.

### Supported File Types & Structures

- **Archive Formats:**
  - `*.tar.gz`, `*.tgz`
  - `*.tar.xz`, `*.txz`
  - `*.tar.bz2`, `*.tbz2`
  - `*.tar`
  - `*.zip`
- **Directory Formats:**
  - **Hyprcursor Theme:** Directory containing `manifest.hl` or `manifest.toml` and a `hyprcursors/` folder.
  - **XCursor Theme:** Directory containing `index.theme` and a `cursors/` folder.
  - **Hybrid Theme:** Directory containing both Hyprcursor and XCursor structures.

### Recommended Download Sources

1. **[GNOME Look (Cursors)](https://www.gnome-look.org/browse?cat=107)** — Extensive repository of community-created XCursor and Hyprcursor themes.
2. **[Pling / OpenDesktop](https://www.pling.com/c/107)** — Popular cursor theme directory.
3. **[Hyprcursor Community Ecosystem](https://github.com/topics/hyprcursor)** — Native vector cursor themes on GitHub.
4. **[Catppuccin Cursors](https://github.com/catppuccin/cursors)** — Official Catppuccin colorway cursor ports.

---

## Importing & Managing Themes

### Using the In-App Importer

1. Open **Cursor Theme** from your application launcher or terminal.
2. Click **Import** in the sidebar header.
3. Browse using the quick shortcuts (`Home`, `Downloads`, `~/.local/share/icons`, `/usr/share/icons`) or navigate directories.
4. Select a supported cursor archive or extracted theme folder and click **Import Theme**.
5. The theme is verified, extracted, converted (if legacy XCursor), and immediately available for preview and application.

### Managing Imported Themes

For any imported theme in the sidebar, hover over the entry or select it to reveal the **`⋯`** context button:
- **Open folder:** Opens the installed directory in your default file manager.
- **Rename:** Opens a modal to safely rename the display title of the theme.
- **Remove:** Prompts confirmation to delete the imported theme and its caches. If the removed theme is currently active, the plugin automatically falls back to the default bundled theme.

### CLI Import & Removal

```bash
# Import an archive or folder
scripts/cursorctl import --source ~/Downloads/Bibata-Modern-Ice.tar.gz

# Rename an imported theme
scripts/cursorctl rename-imported --id CursorSwitcher-Imported-Bibata-1a2b3c --name "Bibata Ice"

# Remove an imported theme
scripts/cursorctl remove-imported --id CursorSwitcher-Imported-Bibata-1a2b3c
```

---

## Security & omarchyplugins.com Compliance

Cursor Theme adheres strictly to Omarchy plugin standards and follows defensive security practices:

- **Untrusted Input Hardening:** All imported archives and folders are treated as untrusted data.
- **No Script Execution:** Cursor Theme never executes `install.sh`, `Makefile`, Python, or shell scripts bundled inside third-party theme archives.
- **Path Traversal Protection:** Extraction strictly validates target paths, forbidding relative directory traversal (`..`), absolute path escapes, device files, FIFOs, and symlinks pointing outside the theme root.
- **Decompression Bomb Protection:** Archive extraction enforces safe file size caps (max 50 MB archive, max 150 MB extracted, max 5,000 files).
- **Safe Subprocess Execution:** All backend scripts execute with parameterized arguments (`subprocess.run(list, ...)`), preventing shell injection.
- **Isolated Namespacing:** Imported themes are installed under isolated namespaces (`~/.local/share/icons/CursorSwitcher-Imported-*`) and will never overwrite system packages or user files.

---

## Bundled Themes & Attributions

Cursor Theme ships with curated, high-quality open-source cursor themes. Each theme is packaged independently, preserving original authorship, copyright notices, vector sources, and licenses:

| Theme | Upstream Project | Author / Creator | License | Sources |
| :--- | :--- | :--- | :--- | :--- |
| **Banana** | [ful1e5/banana-cursor](https://github.com/ful1e5/banana-cursor) | Abdulkaiz Khatri (`ful1e5`) | GPL-3.0 | [`themes/banana/`](themes/banana/) |
| **Phinger** | [phisch/phinger-cursors](https://github.com/phisch/phinger-cursors) | Philipp Schaffrath (`phisch`) | CC BY-SA 4.0 | [`themes/phinger/`](themes/phinger/) |
| **Oreo** | [varlesh/oreo-cursors](https://github.com/varlesh/oreo-cursors) | Alexey Varfolomeev (`varlesh`) | GPL-2.0 | [`themes/oreo/`](themes/oreo/) |
| **Volantes** | [varlesh/volantes-cursors](https://github.com/varlesh/volantes-cursors) | Alexey Varfolomeev (`varlesh`) | GPL-2.0 | [`themes/volantes/`](themes/volantes/) |
| **Nordzy** | [guillaumeboehm/Nordzy-cursors](https://github.com/guillaumeboehm/Nordzy-cursors) | Guillaume Boehm (`gboehm`) | GPL-3.0 | [`themes/nordzy/`](themes/nordzy/) |
| **Capitaine** | [keeferrourke/capitaine-cursors](https://github.com/keeferrourke/capitaine-cursors) | Keefer Rourke (`keeferrourke`) | LGPL-3.0 | [`themes/capitaine/`](themes/capitaine/) |
| **Adwaita** | [GNOME/adwaita-icon-theme](https://gitlab.gnome.org/GNOME/adwaita-icon-theme) | GNOME Project | LGPL-2.1 / CC-BY-SA | `/usr/share/icons/Adwaita` |
| **Bibata Catppuccin** | [catppuccin/cursors](https://github.com/catppuccin/cursors) | Abdulkaiz Khatri & Catppuccin | GPL-3.0 | `/usr/share/icons/Bibata-*` |

See [`THIRD_PARTY.md`](THIRD_PARTY.md) for full licensing architecture, audit logs, and upstream commit provenance.

---

## Removal

To completely remove the plugin:

```bash
omarchy plugin remove sanjyay.cursor-switcher
```

Removal automatically:
1. Restores the pre-existing cursor theme and size captured prior to plugin installation.
2. Cleans up generated application desktop shortcuts, launchers, and icons.
3. Removes UWSM configuration fragments and temporary preview caches.

---

## License

The plugin code and Omarchy integration scripts are licensed under the [GNU General Public License v3.0 or later](LICENSE). Bundled third-party cursor themes retain their respective open-source licenses as documented in [`THIRD_PARTY.md`](THIRD_PARTY.md).
