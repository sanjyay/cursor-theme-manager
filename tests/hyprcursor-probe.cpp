#include <hyprcursor/hyprcursor.hpp>
#include <iostream>

static void log_message(enum eHyprcursorLogLevel, char *) {}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    Hyprcursor::SManagerOptions options;
    options.allowDefaultFallback = false;
    options.logFn = log_message;
    Hyprcursor::CHyprcursorManager manager(argv[1], options);
    if (!manager.valid()) return 3;
    const Hyprcursor::SCursorStyleInfo style{.size = 24};
    if (!manager.loadThemeStyle(style)) return 4;
    const auto check = [&](const char *name, int hotspotX, int hotspotY) {
        const auto shape = manager.getShape(name, style);
        if (shape.images.empty()) return false;
        const auto &image = shape.images.front();
        if (image.hotspotX != hotspotX || image.hotspotY != hotspotY) {
            std::cerr << name << ": hotspot " << image.hotspotX << ',' << image.hotspotY
                      << " (expected " << hotspotX << ',' << hotspotY << ")\n";
            return false;
        }
        return true;
    };
    for (const auto name : {"default", "left_ptr", "arrow", "top_left_arrow"})
        if (!check(name, 3, 2)) return 5;
    for (const auto name : {"pointer", "link", "hand", "hand1", "hand2", "pointing_hand",
                            "9d800788f1b08800ae810202380a0822",
                            "e29285e634086352946a0e7090d73106"})
        if (!check(name, 12, 2)) return 6;
    std::cout << "hyprcursor role aliases and hotspots: ok\n";
    manager.cursorSurfaceStyleDone(style);
    return 0;
}
