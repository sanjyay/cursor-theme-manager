#include <X11/Xcursor/Xcursor.h>
#include <png.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void fail(const char *message, const char *path) {
    fprintf(stderr, "xcursor-pack: %s%s%s\n", message, path ? ": " : "", path ? path : "");
    exit(EXIT_FAILURE);
}

static XcursorImage *load_png(const char *path, int nominal, int xhot, int yhot, int delay) {
    FILE *fp = fopen(path, "rb");
    if (!fp) fail("cannot open PNG", path);
    png_structp png = png_create_read_struct(PNG_LIBPNG_VER_STRING, NULL, NULL, NULL);
    png_infop info = png ? png_create_info_struct(png) : NULL;
    if (!png || !info) fail("cannot initialize libpng", path);
    if (setjmp(png_jmpbuf(png))) fail("invalid PNG", path);
    png_init_io(png, fp);
    png_read_info(png, info);
    png_uint_32 width, height;
    int depth, color;
    png_get_IHDR(png, info, &width, &height, &depth, &color, NULL, NULL, NULL);
    if (width != height || width == 0 || width > 512) fail("cursor PNG must be square and at most 512px", path);
    if (depth == 16) png_set_strip_16(png);
    if (color == PNG_COLOR_TYPE_PALETTE) png_set_palette_to_rgb(png);
    if (color == PNG_COLOR_TYPE_GRAY && depth < 8) png_set_expand_gray_1_2_4_to_8(png);
    if (png_get_valid(png, info, PNG_INFO_tRNS)) png_set_tRNS_to_alpha(png);
    if (color == PNG_COLOR_TYPE_GRAY || color == PNG_COLOR_TYPE_GRAY_ALPHA) png_set_gray_to_rgb(png);
    if (!(color & PNG_COLOR_MASK_ALPHA)) png_set_add_alpha(png, 0xff, PNG_FILLER_AFTER);
    png_read_update_info(png, info);
    png_bytep *rows = calloc(height, sizeof(*rows));
    png_bytep data = malloc(png_get_rowbytes(png, info) * height);
    if (!rows || !data) fail("out of memory", path);
    for (png_uint_32 y = 0; y < height; y++) rows[y] = data + y * png_get_rowbytes(png, info);
    png_read_image(png, rows);
    fclose(fp);

    XcursorImage *image = XcursorImageCreate((int)width, (int)height);
    if (!image) fail("cannot allocate XCursor image", path);
    image->size = nominal;
    image->xhot = xhot;
    image->yhot = yhot;
    image->delay = delay;
    for (png_uint_32 y = 0; y < height; y++) {
        for (png_uint_32 x = 0; x < width; x++) {
            const png_bytep pixel = &rows[y][x * 4];
            image->pixels[y * width + x] = ((uint32_t)pixel[3] << 24) | ((uint32_t)pixel[0] << 16)
                | ((uint32_t)pixel[1] << 8) | pixel[2];
        }
    }
    free(rows);
    free(data);
    png_destroy_read_struct(&png, &info, NULL);
    return image;
}

int main(int argc, char **argv) {
    if (argc < 7 || (argc - 2) % 5 != 0)
        fail("usage: xcursor-pack OUTPUT SIZE XHOT YHOT DELAY PNG [...]", NULL);
    int count = (argc - 2) / 5;
    XcursorImages *images = XcursorImagesCreate(count);
    if (!images) fail("cannot allocate image list", NULL);
    for (int i = 0; i < count; i++) {
        int offset = 2 + i * 5;
        images->images[i] = load_png(argv[offset + 4], atoi(argv[offset]), atoi(argv[offset + 1]),
                                     atoi(argv[offset + 2]), atoi(argv[offset + 3]));
    }
    images->nimage = count;
    FILE *output = fopen(argv[1], "wb");
    if (!output) fail("cannot create output", argv[1]);
    if (!XcursorFileSaveImages(output, images)) fail("libXcursor refused output", argv[1]);
    fclose(output);
    XcursorImagesDestroy(images);
    return EXIT_SUCCESS;
}
