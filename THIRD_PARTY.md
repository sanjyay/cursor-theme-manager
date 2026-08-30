# Third-Party Cursor Themes

Cursor Switcher integrates and bundles high-quality cursor artwork created by independent open-source projects. Each cursor theme is distributed as an independent data component and retains its original license and copyright notices.

Cursor Switcher does not claim original authorship of these designs or endorsement by their respective creators.

---

## Bundled Third-Party Themes

| Theme | Upstream Project | Author / Creator | License | Upstream Commit | Modifications | Local Attribution & License |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Banana** | [ful1e5/banana-cursor](https://github.com/ful1e5/banana-cursor) | Abdulkaiz Khatri (`ful1e5`) | GPL-3.0 | `6d1f8ba67e1547bf1bf5ab6acb43eb3abb5bca9f` | Packaged into standalone Hyprcursor and multi-size XCursor packages (16..256px) preserving upstream SVG artwork and hotspots. | [`themes/banana/ATTRIBUTION.md`](./themes/banana/ATTRIBUTION.md) <br> [`themes/banana/LICENSE`](./themes/banana/LICENSE) |
| **Phinger** | [phisch/phinger-cursors](https://github.com/phisch/phinger-cursors) | Philipp Schaffrath (`phisch`) | CC BY-SA 4.0 | `1e674f9a86d768de9f7dc93bb6d9685e25ce9655` | Packaged dark variant into standalone Hyprcursor (.hlc vector SVGs) and multi-size XCursor packages (16..256px) preserving upstream vector hotspots. | [`themes/phinger/ATTRIBUTION.md`](./themes/phinger/ATTRIBUTION.md) <br> [`themes/phinger/LICENSE`](./themes/phinger/LICENSE) |
| **Oreo** | [varlesh/oreo-cursors](https://github.com/varlesh/oreo-cursors) | Alexey Varfolomeev (`varlesh`) | GPL-2.0-only | `889d1469fbfebe64c4897f2aa2ee6fa620f34080` | Processed `.svg.oreo` template sources into dark colorway SVGs; packaged into standalone Hyprcursor and multi-size XCursor packages (16..256px) preserving upstream hotspots. | [`themes/oreo/ATTRIBUTION.md`](./themes/oreo/ATTRIBUTION.md) <br> [`themes/oreo/LICENSE`](./themes/oreo/LICENSE) |
| **Volantes** | [varlesh/volantes-cursors](https://github.com/varlesh/volantes-cursors) | Alexey Varfolomeev (`varlesh`) | GPL-2.0-only | `b13a4bbf6bd1d7e85fadf7f2ecc44acc198f8d01` | Packaged from upstream dark SVG sources and spec configs into standalone Hyprcursor and multi-size XCursor packages (16..256px) preserving upstream hotspots. | [`themes/volantes/ATTRIBUTION.md`](./themes/volantes/ATTRIBUTION.md) <br> [`themes/volantes/LICENSE`](./themes/volantes/LICENSE) |
| **Nordzy** | [guillaumeboehm/Nordzy-cursors](https://github.com/guillaumeboehm/Nordzy-cursors) <br> [GitLab](https://gitlab.com/gboehm/Nordzy-cursors) | Guillaume Boehm (`gboehm`) | GPL-3.0-only | `c7fc485e9e4fd974c4f4ff9f5f14610fa7835e7b` | Integrated native upstream Hyprcursor and XCursor packages directly without modification. | [`themes/nordzy/ATTRIBUTION.md`](./themes/nordzy/ATTRIBUTION.md) <br> [`themes/nordzy/COPYING`](./themes/nordzy/COPYING) |
| **Capitaine** | [keeferrourke/capitaine-cursors](https://github.com/keeferrourke/capitaine-cursors) | Keefer Rourke (`keeferrourke`) | LGPL-3.0-or-later | `06c88433662a4004cf56a6e471b523a0a8880be0` | Packaged dark variant from upstream vector SVGs and `.spec` configurations into standalone Hyprcursor and multi-size XCursor packages (16..256px). | [`themes/capitaine/ATTRIBUTION.md`](./themes/capitaine/ATTRIBUTION.md) <br> [`themes/capitaine/COPYING`](./themes/capitaine/COPYING) |

---

## Licensing Architecture & Isolation

- **Independent Data Components**: Each cursor theme directory under `themes/` and `third_party/` contains its own full upstream license, author notices, commit hash, and corresponding source.
- **No Blanket Relicensing**: The root plugin's GPL license is not applied across third-party works. GPL-2.0 works (`Oreo`, `Volantes`) remain strictly GPL-2.0, LGPL-3.0 works (`Capitaine`) remain LGPL-3.0, and CC-BY-SA 4.0 works (`Phinger`) remain under Creative Commons Attribution-ShareAlike 4.0 terms.
- **Corresponding Source Availability**: Source SVG files, template generators, and configuration specs for all bundled packages are preserved locally in the repository to satisfy source availability and redistribution terms.
