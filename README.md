# Cursor Theme Manager

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](manifest.json)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Hyprland%20%7C%20Omarchy-purple.svg)](https://omarchyplugins.com)

Cursor Theme Manager is a local-first cursor theme manager and previewer for Omarchy and Hyprland. It discovers themes already installed on your system, provides dynamic multi-role previews, cursor sizing, hover inspection, safe archive/folder importing, and management of themes imported through the plugin.

> [!NOTE]
> **Local-Only Architecture:** Cursor Theme Manager does not bundle, ship with, or automatically download third-party cursor themes. It operates strictly locally with zero runtime network requests and zero automatic downloads.

---

## Features

- **Local Theme Discovery:** Scans standard system icon directories (`/usr/share/icons`, `/usr/local/share/icons`, `$XDG_DATA_DIRS/icons`) and user directories (`~/.local/share/icons`, `~/.icons`).
- **Clear Theme Classification:** Accurately categorizes discovered themes into **System**, **User**, and **Imported** sources.
- **Dynamic Role Previews:** Automatically extracts and renders preview cards for semantic cursor roles (`Default`, `Pointer`, `Text`, `Move`, `Resize`, `Wait`). If a theme does not define a role (e.g., static themes without an animated `Wait` cursor), the card is omitted gracefully and remaining previews automatically reflow and center.
- **Accurate Hotspot Indicators:** Hovering any preview card displays a subtle indicator (`•`) at the exact hotspot coordinate defined by the Hyprcursor or XCursor metadata.
- **Hover-to-Preview:** Browse themes in the sidebar to temporarily inspect preview cards and metadata without modifying active session settings. Clicking applies and commits the theme.
- **Synchronized Size Control:** Stepper buttons (`−` / `+`) paired with a discrete slider track supporting standard scale snap points (16, 20, 24, 28, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256 px).
- **In-App Native Importer:** Built-in modal file browser matching Omarchy design tokens for importing local directories or archives (`.tar.gz`, `.tar.xz`, `.zip`, etc.) chosen explicitly by the user.
- **Automatic Hyprcursor Compilation:** Legacy XCursor themes are automatically converted to native Hyprcursor packages on-the-fly using `hyprcursor-util`.
- **Safe Imported-Theme Management:** Rename, open directory, or safely remove themes imported through the plugin directly from the UI or CLI. Destructive actions are restricted strictly to plugin-owned imported themes.
- **Compositor-Aware Persistence:** Instantly applies changes via `hyprctl setcursor` and `gsettings`, updating UWSM environment files (`~/.config/uwsm/env.d/90-omarchy-cursor-switcher`) and D-Bus activation environments for new applications.
- **Optional Desktop Integration:** Optional user-consented desktop integration installs desktop entries (`omarchy-cursor-switcher.desktop`) and terminal launcher commands (`omarchy-cursor-switcher`) with transactional installation and clean rollback.
- **Hardened Subprocess Supervisor:** Bounded stream selectors, strict wall-clock deadlines, and process-group isolation ensure child tools cannot exhaust memory or orphan background processes.
- **Descriptor-Held Private State:** Secure state directory (`$XDG_STATE_HOME/cursor-theme-manager/`, mode `0700`) with descriptor-held durable writes and schema validation.
- **Zero Network Access:** Operates completely offline with zero runtime network requests, downloads, or background telemetry.
- **Fully Responsive:** Fluid layouts designed for full-screen, split tiled (50/50), or compact floating windows.

---

## Theme Discovery & Classification

Cursor Theme Manager automatically scans local icon-theme directories on launch and rescan:

- `~/.local/share/icons` (`$XDG_DATA_HOME/icons`)
- `~/.icons`
- `/usr/share/icons`
- `/usr/local/share/icons`
- `$XDG_DATA_DIRS/icons`

> [!IMPORTANT]
> No cursor themes are installed merely by installing or launching Cursor Theme Manager. The plugin operates exclusively on themes present in these local directories.

### Theme Classification Model

| Source | Description | Management Permissions |
| :--- | :--- | :--- |
| **System** | Themes installed system-wide in `/usr/share/icons`, `/usr/local/share/icons`, or `$XDG_DATA_DIRS/icons`. | Read-only. Preview and apply only. |
| **User** | Themes present in `~/.local/share/icons` or `~/.icons` installed manually or via package managers outside this plugin. | Read-only. Preview and apply only. |
| **Imported** | Themes explicitly imported through Cursor Theme Manager and stored in `~/.local/share/icons/CursorSwitcher-Imported-*` with a plugin metadata marker. | Full management (Preview, Apply, Open Folder, Rename, Remove). |

---

## Installation

### Via Omarchy CLI

```bash
omarchy plugin add https://github.com/sanjyay/cursor-theme-manager --enable
```

> **Note:** Installing Cursor Theme Manager does not install any cursor themes. Existing themes on the system are discovered automatically.

### Manual / Local Development

Clone or symlink the repository into your Omarchy plugins directory:

```bash
git clone https://github.com/sanjyay/cursor-theme-manager.git ~/.config/omarchy/plugins/sanjyay.cursor-theme-manager
omarchy-shell shell rescanPlugins
omarchy plugin enable sanjyay.cursor-theme-manager
```

---

## Launching & Configuring

Cursor Theme Manager integrates with standard Omarchy shell controls:

- **Omarchy Shell IPC:**
  ```bash
  omarchy-shell shell summon sanjyay.cursor-theme-manager '{}'
  omarchy-shell shell toggle sanjyay.cursor-theme-manager '{}'
  omarchy-shell shell hide sanjyay.cursor-theme-manager
  ```
- **Optional Desktop Entry & CLI:** Enable **Desktop Integration** from within the in-app settings modal to install `omarchy-cursor-switcher.desktop` and the `omarchy-cursor-switcher` CLI command.

---

## Keyboard Navigation

| Key | Action |
| :--- | :--- |
| **Up / Down** (`k` / `j`) | Navigate theme list |
| **Left / Right** (`h` / `l`) | Decrease / increase cursor size (when size focused) |
| **Tab / Shift+Tab** | Switch focus between theme list and size stepper |
| **Enter / Space** | Apply and commit focused theme / confirm dialog |
| **Escape** | Close dialogs or close panel |
| **r** | Refresh / rescan installed cursor themes |

---

## Getting Additional Cursor Themes

Cursor Theme Manager does not download themes itself. To add new cursor themes:

1. Browse and select an upstream open-source cursor project.
2. Download the theme release archive (or clone the repository) locally to your machine.
3. Open **Cursor Theme Manager** and click **Import** in the header.
4. Browse your local storage and select the downloaded archive or extracted folder.
5. Click **Import Theme**. Cursor Theme Manager verifies safety, stages the files, converts XCursor to Hyprcursor if needed, and adds the theme to your library.

### Supported Archive & Directory Formats

- **Archives:** `.tar.gz`, `.tgz`, `.tar.xz`, `.txz`, `.tar.bz2`, `.tbz2`, `.tar`, `.zip`
- **Directories:** Any folder containing a native Hyprcursor (`manifest.hl`) or XCursor (`cursors/` directory with `index.theme`).

---

## Recommended Cursor Themes

The following popular open-source cursor themes are compatible with Cursor Theme Manager.

> [!NOTE]
> These projects are independent third-party themes. Cursor Theme Manager does not bundle, maintain, or automatically install these themes. Review the upstream projects and releases before downloading.

| Theme | Author / Project | License | Upstream Project |
| :--- | :--- | :--- | :--- |
| **Banana** | Abdulkaiz Khatri (`ful1e5`) | GPL-3.0 | [ful1e5/banana-cursor](https://github.com/ful1e5/banana-cursor) |
| **Phinger** | Philipp Schaffrath (`phisch`) | CC-BY-SA-4.0 | [phisch/phinger-cursors](https://github.com/phisch/phinger-cursors) |
| **Oreo** | Alexey Varfolomeev (`varlesh`) | GPL-2.0 | [varlesh/oreo-cursors](https://github.com/varlesh/oreo-cursors) |
| **Volantes** | Alexey Varfolomeev (`varlesh`) | GPL-2.0 | [varlesh/volantes-cursors](https://github.com/varlesh/volantes-cursors) |
| **Nordzy** | Guillaume Boehm (`gboehm`) | GPL-3.0 | [guillaumeboehm/Nordzy-cursors](https://github.com/guillaumeboehm/Nordzy-cursors) |
| **Capitaine** | Keefer Rourke (`keeferrourke`) | LGPL-3.0 | [keeferrourke/capitaine-cursors](https://github.com/keeferrourke/capitaine-cursors) |
| **Bibata** | Abdulkaiz Khatri (`ful1e5`) | GPL-3.0 | [ful1e5/Bibata_Cursor](https://github.com/ful1e5/Bibata_Cursor) |
| **Catppuccin** | Catppuccin Community | GPL-3.0 | [catppuccin/cursors](https://github.com/catppuccin/cursors) |

---

## Managing Imported Themes & Ownership Safety

Cursor Theme Manager enforces strict ownership boundaries:

- **Non-Destructive for System and User Themes:** Cursor Theme Manager never modifies, renames, or deletes system themes or general user themes in `~/.local/share/icons` and `~/.icons`.
- **Plugin-Owned Imported Themes:** Only themes explicitly imported through the plugin (identified by `.omarchy-cursor-switcher-imported` within the `CursorSwitcher-Imported-*` directory) expose management actions:
  - **Open folder:** Opens the installed theme directory in your default file manager.
  - **Rename:** Modifies the display title and theme manifests cleanly.
  - **Remove:** Deletes the imported theme directory and associated preview caches.
- **Active Theme Removal Fallback:** If an imported theme currently in use is removed, Cursor Theme Manager automatically falls back to the first available discovered theme to ensure cursor continuity.

### CLI Management

```bash
# Import a local archive or directory
scripts/cursorctl import --source ~/Downloads/Bibata-Modern-Classic.tar.xz

# Rename an imported theme
scripts/cursorctl rename-imported --id CursorSwitcher-Imported-Bibata-1a2b3c4d5e6f --name "Bibata Classic"

# Remove an imported theme
scripts/cursorctl remove-imported --id CursorSwitcher-Imported-Bibata-1a2b3c4d5e6f
```

---

## Architecture & Security Hardening

```
Local Filesystem Icon Directories (~/.local/share/icons, /usr/share/icons, etc.)
  │
  ▼
Local Discovery & Classification (System / User / Imported)
  │
  ▼
Multi-Role Preview Generation & Hotspot Metadata Extraction
  │
  ▼
Compositor-Aware Application (hyprctl setcursor, gsettings, UWSM env, D-Bus)
```

Cursor Theme Manager adheres strictly to defensive security standards:

- **Zero Runtime Network Access:** No automatic downloads, curl/wget execution, or remote dependencies.
- **Centralized Bounded Process Supervision:** All external subprocesses (`hyprcursor-util`, `xcur2png`, `gsettings`, `systemctl`, `hyprctl`, `xdg-open`) run in isolated process groups under `runtime_safety.run_bounded` with hard memory and wall-clock limits. Exceeding byte limits immediately terminates the process group.
- **Private Descriptor-Held State:** State is stored in a private directory (`$XDG_STATE_HOME/cursor-theme-manager/`, mode `0700`) and written relative to an open directory descriptor (`dir_fd`) with `fsync`, preventing symlink race attacks.
- **Transactional Integration with Rollback:** Optional desktop integration uses staged transactional file operations with automatic rollback if any stage fails.
- **Non-Destructive Restoration:** Restoration strictly limits scope to allowlisted cursor variables and never executes arbitrary resets if snapshot data is missing or invalid.
- **Strict Plain-Text UI:** Every dynamic user-interface text sink explicitly enforces `textFormat: Text.PlainText`.
- **Decompression Bomb Protection:**
  - Maximum archive size: **100 MB**
  - Maximum extracted content size: **750 MB**
  - Maximum file count: **10,000 files**

---

## Removal & Cleanup

To completely remove the plugin:

```bash
omarchy plugin remove sanjyay.cursor-theme-manager
```

Removal automatically:
1. Restores the pre-existing cursor theme and size captured prior to plugin installation.
2. Cleans up generated application desktop shortcuts, launchers, and icons.
3. Removes UWSM configuration fragments and temporary preview caches.

---

## License

Cursor Theme Manager is licensed under the [GNU General Public License v3.0 or later](LICENSE).

Third-party cursor themes linked in documentation are independent projects distributed under their respective upstream licenses; they are not included with or distributed by Cursor Theme Manager.
