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

    // Test size 24
    {
        const Hyprcursor::SCursorStyleInfo style{.size = 24};
        if (!manager.loadThemeStyle(style)) return 4;
        const auto check = [&](const char *name, int hotspotX, int hotspotY) {
            const auto shape = manager.getShape(name, style);
            if (shape.images.empty()) return false;
            const auto &image = shape.images.front();
            if (image.hotspotX != hotspotX || image.hotspotY != hotspotY) {
                std::cerr << name << " @ 24px: hotspot " << image.hotspotX << ',' << image.hotspotY
                          << " (expected " << hotspotX << ',' << hotspotY << ")\n";
                return false;
            }
            return true;
        };
        for (const auto name : {"default", "left_ptr", "arrow", "top_left_arrow"})
            if (!check(name, 5, 5)) return 5;
        for (const auto name : {"hand2", "pointer", "pointing_hand",
                                "9d800788f1b08800ae810202380a0822",
                                "e29285e634086352946a0e7090d73106"})
            if (!check(name, 4, 4)) return 6;
        manager.cursorSurfaceStyleDone(style);
    }

    // Test size 256
    {
        const Hyprcursor::SCursorStyleInfo style{.size = 256};
        if (!manager.loadThemeStyle(style)) return 7;
        const auto check = [&](const char *name, int hotspotX, int hotspotY) {
            const auto shape = manager.getShape(name, style);
            if (shape.images.empty()) return false;
            const auto &image = shape.images.front();
            if (image.hotspotX != hotspotX || image.hotspotY != hotspotY) {
                std::cerr << name << " @ 256px: hotspot " << image.hotspotX << ',' << image.hotspotY
                          << " (expected " << hotspotX << ',' << hotspotY << ")\n";
                return false;
            }
            return true;
        };
        for (const auto name : {"default", "left_ptr", "arrow", "top_left_arrow"})
            if (!check(name, 52, 50)) return 8;
        for (const auto name : {"hand2", "pointer", "pointing_hand",
                                "9d800788f1b08800ae810202380a0822",
                                "e29285e634086352946a0e7090d73106"})
            if (!check(name, 39, 45)) return 9;
        manager.cursorSurfaceStyleDone(style);
    }

    std::cout << "hyprcursor role aliases and hotspots at 24px and 256px: ok\n";
    return 0;
}
