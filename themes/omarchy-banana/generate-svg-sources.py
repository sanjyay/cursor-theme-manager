#!/usr/bin/env python3
"""Generate the canonical, clean-room Omarchy Banana SVG source family."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "source"

PALETTE = {
    "body": "#F7C948",
    "highlight": "#FFE58A",
    "flesh": "#FFF0B8",
    "stem": "#795548",
    "outline": "#3E2723",
    "accent": "#D99B24",
}


def svg(body: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <g fill="none" stroke="{PALETTE['outline']}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
{body}
  </g>
</svg>
'''


def banana(transform=""):
    attr = f' transform="{transform}"' if transform else ""
    return f'''    <g{attr}>
      <path fill="{PALETTE['body']}" d="M7 6c10 4 18 13 18 23 0 8 4 14 10 17 5 2 9-1 12-6 1 9-4 16-12 19-11 3-23-3-29-13-6-11-4-23 0-32 2-4 2-6 1-8Z"/>
      <path stroke="{PALETTE['highlight']}" stroke-width="3" d="M11 13c0 13 3 26 15 35"/>
      <path stroke="{PALETTE['accent']}" stroke-width="3" d="M16 52c8 8 21 6 28-3"/>
      <path fill="{PALETTE['stem']}" d="m5 6 2-4 5 3-2 5Z"/>
    </g>'''


def peeled_banana():
    """A distinct link cursor: exposed fruit above three folded peel flaps."""
    return f'''    <path fill="{PALETTE['flesh']}" d="M32 5c6 4 9 13 7 23-1 8-4 14-8 19-5-7-8-16-7-26 1-8 4-14 8-16Z"/>
    <path fill="{PALETTE['body']}" d="M27 32c-4 6-10 10-18 13 4 8 10 11 18 8-3-7-2-14 3-20Z"/>
    <path fill="{PALETTE['body']}" d="M36 32c5 5 11 9 19 11-2 9-8 13-17 10 3-7 2-14-4-20Z"/>
    <path fill="{PALETTE['highlight']}" d="M29 38c-1 7 0 14 3 20 4-6 6-13 3-20Z"/>
    <path stroke="{PALETTE['highlight']}" stroke-width="2.5" d="M15 46c3 4 7 5 10 4m24-5c-3 4-6 6-10 5"/>
    <path fill="{PALETTE['stem']}" d="m29 6 2-4 5 2-1 5Z"/>'''


def arrow_overlay(symbol: str):
    glyphs = {
        "copy": f'<path fill="{PALETTE["body"]}" d="M38 38h18v18H38Z"/><path d="M42 47h10M47 42v10"/>',
        "alias": f'<path fill="{PALETTE["body"]}" d="M36 42h18v14H36Z"/><path d="m40 51 10-7m0 0h-7m7 0v7"/>',
        "help": f'<circle fill="{PALETTE["body"]}" cx="47" cy="47" r="10"/><path d="M43 44c0-5 8-5 8 0 0 3-4 3-4 6m0 3v1"/>',
        "context": f'<rect fill="{PALETTE["body"]}" x="36" y="39" width="22" height="17" rx="3"/><path d="M42 44h10m-10 6h7"/>'
    }
    return banana("scale(.82)") + "\n    " + glyphs[symbol]


def resize(rotation=0, double=False):
    middle = '<circle fill="%s" cx="32" cy="32" r="5"/>' % PALETTE["accent"]
    lower = '<path fill="%s" d="m32 59-11-14h7V32h8v13h7Z"/>' % PALETTE["body"] if double else ""
    return f'''    <g transform="rotate({rotation} 32 32)">
      <path fill="{PALETTE['body']}" d="m32 5 11 14h-7v17h-8V19h-7Z"/>
      {lower}
      {middle}
      <path stroke="{PALETTE['highlight']}" stroke-width="2.5" d="m32 11 4 6h-3"/>
    </g>'''


SOURCES = {
    "default.svg": banana(),
    "pointer.svg": peeled_banana(),
    "text.svg": f'''    <path fill="{PALETTE['body']}" d="M20 7h24v8h-8v34h8v8H20v-8h8V15h-8Z"/>
    <path stroke="{PALETTE['highlight']}" stroke-width="2" d="M24 11h16M24 53h16"/>''',
    "vertical-text.svg": f'''    <path fill="{PALETTE['body']}" d="M7 20h8v8h34v-8h8v24h-8v-8H15v8H7Z"/>
    <path stroke="{PALETTE['highlight']}" stroke-width="2" d="M11 24v16m42-16v16"/>''',
    "crosshair.svg": f'''    <circle fill="{PALETTE['body']}" cx="32" cy="32" r="8"/>
    <path stroke-width="5" d="M32 5v18m0 18v18M5 32h18m18 0h18"/><circle fill="{PALETTE['highlight']}" stroke-width="2" cx="32" cy="32" r="2.5"/>''',
    "cell.svg": f'''    <path fill="{PALETTE['body']}" d="M27 7h10v20h20v10H37v20H27V37H7V27h20Z"/>
    <path stroke="{PALETTE['highlight']}" stroke-width="2" d="M32 12v40M12 32h40"/>''',
    "grab.svg": f'''    <path fill="{PALETTE['body']}" d="M31 31C22 18 11 16 8 25c8-1 12 4 15 11-2-16 5-25 12-19-4 7-3 13-1 19 1-14 10-22 16-15-6 6-7 12-8 20 5-10 13-12 16-5-9 16-21 22-33 17C15 48 12 37 8 25"/>
    <path stroke="{PALETTE['highlight']}" stroke-width="2" d="M19 30c3 5 4 10 6 16m8-20 2 19m11-14-5 15"/>''',
    "grabbing.svg": f'''    <path fill="{PALETTE['body']}" d="M14 27c4-6 10-3 14 3-1-10 6-15 11-9l-2 10c4-8 11-8 14-2l-5 10c6-5 12-1 10 5-8 13-19 17-31 11-10-5-16-20-11-28Z"/>
    <path stroke="{PALETTE['highlight']}" stroke-width="2" d="m25 36 4 11m8-12 1 13m8-10-3 10"/>''',
    "move.svg": f'''    <path fill="{PALETTE['body']}" d="m32 4 11 14h-7v10h10v-7l14 11-14 11v-7H36v10h7L32 60 21 46h7V36H18v7L4 32l14-11v7h10V18h-7Z"/>
    <circle fill="{PALETTE['highlight']}" cx="32" cy="32" r="4" stroke-width="2"/>''',
    "wait.svg": f'''    <circle cx="32" cy="32" r="22" stroke="{PALETTE['accent']}" stroke-width="7" stroke-dasharray="12 7"/>
    <path fill="{PALETTE['body']}" d="M31 8c9 1 16 5 20 12l-8 5c-3-5-7-7-13-8Z"/>
    <circle fill="{PALETTE['highlight']}" cx="32" cy="32" r="5"/>''',
    "progress.svg": banana("scale(.72)") + f'''\n    <circle cx="47" cy="47" r="11" stroke="{PALETTE['accent']}" stroke-width="5" stroke-dasharray="8 5"/>
    <path fill="{PALETTE['body']}" d="m46 35 7 4-5 6-6-4Z"/>''',
    "not-allowed.svg": f'''    {banana("translate(8 8) scale(.75)")}
    <circle cx="32" cy="32" r="23" stroke="#B53A31" stroke-width="8"/><path stroke="#B53A31" stroke-width="8" d="m16 16 32 32"/>''',
    "copy.svg": arrow_overlay("copy"),
    "alias.svg": arrow_overlay("alias"),
    "help.svg": arrow_overlay("help"),
    "context-menu.svg": arrow_overlay("context"),
    "zoom-in.svg": f'''    <circle fill="{PALETTE['body']}" cx="25" cy="25" r="17"/><path d="m38 38 17 17M17 25h16m-8-8v16"/><path stroke="{PALETTE['highlight']}" stroke-width="2" d="M14 18c5-8 15-10 22-3"/>''',
    "zoom-out.svg": f'''    <circle fill="{PALETTE['body']}" cx="25" cy="25" r="17"/><path d="m38 38 17 17M17 25h16"/><path stroke="{PALETTE['highlight']}" stroke-width="2" d="M14 18c5-8 15-10 22-3"/>''',
    "n-resize.svg": resize(0), "s-resize.svg": resize(180), "e-resize.svg": resize(90), "w-resize.svg": resize(-90),
    "ne-resize.svg": resize(45), "nw-resize.svg": resize(-45), "se-resize.svg": resize(135), "sw-resize.svg": resize(-135),
    "ew-resize.svg": resize(90, True), "ns-resize.svg": resize(0, True), "nesw-resize.svg": resize(45, True), "nwse-resize.svg": resize(-45, True),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    expected = set(SOURCES)
    for stale in OUT.glob("*.svg"):
        if stale.name not in expected:
            stale.unlink()
    for name, body in sorted(SOURCES.items()):
        (OUT / name).write_text(svg(body), encoding="utf-8")
    print(f"generated {len(SOURCES)} canonical SVGs in {OUT}")


if __name__ == "__main__":
    main()
