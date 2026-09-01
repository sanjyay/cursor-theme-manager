# Cursor Theme Manager

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](manifest.json)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Hyprland%20%7C%20Omarchy-purple.svg)](https://omarchyplugins.com)

Cursor Theme Manager is a local-first cursor theme manager and previewer for Omarchy and Hyprland. It discovers themes already installed on your system, provides dynamic multi-role previews, cursor sizing, hover inspection, safe archive/folder importing, and management of themes imported through the plugin.

> [!NOTE]
> **Local-Only Architecture:** Cursor Theme Manager does not bundle, ship with, or automatically download third-party cursor themes. It operates strictly locally with zero runtime network requests and zero automatic downloads.

---

## Features

- **Standalone Application:** Installs a desktop entry (`Cursor Theme Manager`) and launcher command (`omarchy-cursor-switcher`). Open and configure your cursor directly from your application launcher or terminal.
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

Cursor Theme Manager integrates with standard desktop launchers and Omarchy shell controls:

- **Application Launcher:** Open your application launcher (Omarchy drawer, Rofi, Fuzzel, etc.) and search for **Cursor Theme Manager** (or *Cursor Theme*, *Mouse*, *Pointer*).
- **Command Line:** Run `omarchy-cursor-switcher` from any terminal.
- **Omarchy Shell IPC:**
  ```bash
  omarchy-shell shell summon sanjyay.cursor-theme-manager '{}'
  omarchy-shell shell toggle sanjyay.cursor-theme-manager '{}'
  omarchy-shell shell hide sanjyay.cursor-theme-manager
  ```

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

### Installing Recommended Themes

Cursor Theme Manager does not download these themes automatically. The commands below are optional convenience instructions using each project's upstream distribution method. Review the upstream project before installing or downloading a theme.

<details>
<summary><strong>Banana</strong> — ful1e5</summary>

**Upstream:** [ful1e5/banana-cursor](https://github.com/ful1e5/banana-cursor) • **Version:** v2.0.0

**Option 1 — Arch/AUR**

```bash
yay -S banana-cursor-bin
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Official Release Archive**

```bash
curl -fL \
  -o ~/Downloads/Banana.tar.xz \
  'https://github.com/ful1e5/banana-cursor/releases/download/v2.0.0/Banana.tar.xz'
```

*Optional integrity check:*
```bash
echo "9d2c4003315b3fc39b47c52dbfd6211d499db154b0fbb1c3c4dd9c0023561bf0  $HOME/Downloads/Banana.tar.xz" | sha256sum -c -
```

Then in Cursor Theme Manager: `Import → Downloads → Banana.tar.xz`

</details>

<details>
<summary><strong>Phinger</strong> — phisch</summary>

**Upstream:** [phisch/phinger-cursors](https://github.com/phisch/phinger-cursors) • **Version:** v2.1

**Option 1 — Arch/AUR**

```bash
yay -S phinger-cursors
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Official Release Archive**

```bash
curl -fL \
  -o ~/Downloads/phinger-cursors-variants.tar.bz2 \
  'https://github.com/phisch/phinger-cursors/releases/download/v2.1/phinger-cursors-variants.tar.bz2'
```

*Optional integrity check:*
```bash
echo "ddb7310c62bf8e0e2798a24f8a867e4af7b17a39757ba45c85e13f3988f646fc  $HOME/Downloads/phinger-cursors-variants.tar.bz2" | sha256sum -c -
```

Then in Cursor Theme Manager: `Import → Downloads → phinger-cursors-variants.tar.bz2`

</details>

<details>
<summary><strong>Oreo</strong> — varlesh</summary>

**Upstream:** [varlesh/oreo-cursors](https://github.com/varlesh/oreo-cursors)

**Option 1 — Arch/AUR**

```bash
yay -S oreo-cursors-bin
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Upstream Release Download**

Upstream distributes pre-built packages through Pling / OpenDesktop:

1. Download the desired color variant from the upstream [Oreo Cursors Pling Page](https://www.pling.com/p/1360254/).
2. In Cursor Theme Manager, choose `Import` and select the downloaded archive.

</details>

<details>
<summary><strong>Volantes</strong> — varlesh</summary>

**Upstream:** [varlesh/volantes-cursors](https://github.com/varlesh/volantes-cursors)

**Option 1 — Arch/AUR**

```bash
yay -S volantes-cursors
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Upstream Release Download**

Upstream distributes pre-built archives through Pling / OpenDesktop:

1. Download the desired variant archive from the upstream [Volantes Cursors Pling Page](https://www.pling.com/p/1356095/).
2. In Cursor Theme Manager, choose `Import` and select the downloaded archive.

</details>

<details>
<summary><strong>Nordzy</strong> — gboehm</summary>

**Upstream:** [guillaumeboehm/Nordzy-cursors](https://github.com/guillaumeboehm/Nordzy-cursors) • **Version:** v2.4.0

**Option 1 — Arch/AUR**

```bash
yay -S nordzy-cursors
# or for native hyprcursors:
yay -S nordzy-hyprcursors
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Official Release Archive**

For XCursor:
```bash
curl -fL \
  -o ~/Downloads/Nordzy-cursors.tar.gz \
  'https://github.com/guillaumeboehm/Nordzy-cursors/releases/download/v2.4.0/Nordzy-cursors.tar.gz'
```

*Optional integrity check:*
```bash
echo "3451c1221d58562a5eb647c45f3f7b5e2bbfe0aacf10d9cbc899bc36e5239e5a  $HOME/Downloads/Nordzy-cursors.tar.gz" | sha256sum -c -
```

For native Hyprcursor:
```bash
curl -fL \
  -o ~/Downloads/Nordzy-hyprcursors.tar.gz \
  'https://github.com/guillaumeboehm/Nordzy-cursors/releases/download/v2.4.0/Nordzy-hyprcursors.tar.gz'
```

*Optional integrity check:*
```bash
echo "d13767cd6d4757ddc3722e407d7a5f3422a4e4cce231495b7cf4d1be3e7a8b35  $HOME/Downloads/Nordzy-hyprcursors.tar.gz" | sha256sum -c -
```

Then in Cursor Theme Manager: `Import → Downloads → Nordzy-*.tar.gz`

</details>

<details>
<summary><strong>Capitaine</strong> — keeferrourke</summary>

**Upstream:** [keeferrourke/capitaine-cursors](https://github.com/keeferrourke/capitaine-cursors) • **Arch Package:** `extra/capitaine-cursors` (v4-3)

**Option 1 — Official Arch Repository (Recommended)**

```bash
sudo pacman -S capitaine-cursors
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Upstream Release Download**

1. Download pre-compiled variant packages from the upstream [Capitaine Cursors Pling Page](https://www.pling.com/p/1148692/).
2. In Cursor Theme Manager, choose `Import` and select the downloaded archive.

</details>

<details>
<summary><strong>Bibata</strong> — ful1e5</summary>

**Upstream:** [ful1e5/Bibata_Cursor](https://github.com/ful1e5/Bibata_Cursor) • **Version:** v2.0.7

**Option 1 — Arch/AUR**

```bash
yay -S bibata-cursor-theme-bin
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Official Release Archive**

```bash
curl -fL \
  -o ~/Downloads/Bibata-Modern-Classic.tar.xz \
  'https://github.com/ful1e5/Bibata_Cursor/releases/download/v2.0.7/Bibata-Modern-Classic.tar.xz'
```

*Optional integrity check:*
```bash
echo "7d3495864e5bbef02f5e77de760b2905903b63c71495a78ef6306d19a3b556d8  $HOME/Downloads/Bibata-Modern-Classic.tar.xz" | sha256sum -c -
```

Then in Cursor Theme Manager: `Import → Downloads → Bibata-Modern-Classic.tar.xz`

*(All variants archive: `Bibata.tar.xz`)*

</details>

<details>
<summary><strong>Catppuccin</strong> — Catppuccin</summary>

**Upstream:** [catppuccin/cursors](https://github.com/catppuccin/cursors) • **Version:** v2.0.0

**Option 1 — Arch/AUR**

```bash
yay -S catppuccin-cursors-mocha
# or: yay -S catppuccin-cursors-latte catppuccin-cursors-frappe catppuccin-cursors-macchiato
```

Reopen or refresh Cursor Theme Manager. The theme will be discovered automatically.

**Option 2 — Official Release Archive**

```bash
curl -fL \
  -o ~/Downloads/catppuccin-mocha-dark-cursors.zip \
  'https://github.com/catppuccin/cursors/releases/download/v2.0.0/catppuccin-mocha-dark-cursors.zip'
```

*Optional integrity check:*
```bash
echo "a4d976491bdb1b1311b2de88327cad3f1c66c2d9da896e0c56362a660c802585  $HOME/Downloads/catppuccin-mocha-dark-cursors.zip" | sha256sum -c -
```

Then in Cursor Theme Manager: `Import → Downloads → catppuccin-mocha-dark-cursors.zip`

</details>

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

## Architecture

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

```
User-Selected Local Archive / Folder
  │
  ▼
Security Validation & Sandbox Extraction
  │
  ▼
XCursor → Hyprcursor Compilation (via hyprcursor-util if needed)
  │
  ▼
Atomic Install to ~/.local/share/icons/CursorSwitcher-Imported-*
```

---

## Security & Import Hardening

Cursor Theme Manager adheres strictly to defensive security standards:

- **Zero Runtime Network Access:** No automatic downloads, curl/wget execution, or remote dependencies.
- **Untrusted Input Hardening:** All user-provided archives and directories are validated and isolated prior to extraction.
- **No Script Execution:** Cursor Theme Manager never executes installer scripts (`install.sh`, `setup.sh`, `Makefile`, `.sh`, `.exe`, `.bat`, etc.) inside theme archives.
- **Path Traversal Protection:** Extraction strictly forbids relative directory traversal (`..`), absolute paths, device nodes, FIFOs, and symlinks pointing outside the theme directory.
- **Resource Limits:** Enforces decompression caps to prevent decompression bombs:
  - Maximum archive size: **100 MB**
  - Maximum extracted content size: **750 MB**
  - Maximum file count: **10,000 files**
- **Atomic Operations:** Installs and renames use temporary staging directories with atomic POSIX replacement operations.
- **Protected Destructive Actions:** Remove and Rename operations are strictly restricted to themes managed by Cursor Theme Manager (verified via `.omarchy-cursor-switcher-imported`), preventing accidental deletion of system or user files.

---

## Removal

To completely remove the plugin:

```bash
omarchy plugin remove sanjyay.cursor-theme-manager
```

Removal automatically:
1. Restores the pre-existing cursor theme and size captured prior to plugin installation (or system default if none was captured).
2. Cleans up generated application desktop shortcuts, launchers, and icons.
3. Removes UWSM configuration fragments and temporary preview caches.

---

## License

Cursor Theme Manager is licensed under the [GNU General Public License v3.0 or later](LICENSE).

Third-party cursor themes linked in documentation are independent projects distributed under their respective upstream licenses; they are not included with or distributed by Cursor Theme Manager.
