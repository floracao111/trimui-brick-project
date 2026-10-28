/* Stretch Hello: shows the pixel-art banana on the Brick Pro's screen, plus a marker you move with the stick.
 * It draws straight to /dev/fb0 and reads /dev/input/js0, so it needs no libraries (it is built static).
 * Any button quits, and so does waiting 25 seconds. */
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/joystick.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include "banana.h"

static uint32_t pack(const struct fb_var_screeninfo *v, int r, int g, int b) {
    return ((uint32_t)r >> (8 - v->red.length) << v->red.offset) |
           ((uint32_t)g >> (8 - v->green.length) << v->green.offset) |
           ((uint32_t)b >> (8 - v->blue.length) << v->blue.offset) |
           (v->transp.length ? (0xFFu >> (8 - v->transp.length) << v->transp.offset) : 0);
}

int main(void) {
    int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) { perror("open /dev/fb0"); return 1; }
    struct fb_var_screeninfo v; struct fb_fix_screeninfo f;
    if (ioctl(fb, FBIOGET_VSCREENINFO, &v) || ioctl(fb, FBIOGET_FSCREENINFO, &f)) { perror("fb info"); return 1; }
    printf("fb: %ux%u virtual %ux%u bpp %u line %u yoffset %u rgb offsets %u/%u/%u lengths %u/%u/%u transp %u/%u\n",
           v.xres, v.yres, v.xres_virtual, v.yres_virtual, v.bits_per_pixel, f.line_length, v.yoffset,
           v.red.offset, v.green.offset, v.blue.offset, v.red.length, v.green.length, v.blue.length,
           v.transp.offset, v.transp.length);
    if (v.bits_per_pixel != 32) { fprintf(stderr, "expected 32 bits per pixel\n"); return 1; }
    size_t size = (size_t)f.line_length * v.yres_virtual;
    uint8_t *mem = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0);
    if (mem == MAP_FAILED) { perror("mmap"); return 1; }
    v.yoffset = 0; ioctl(fb, FBIOPAN_DISPLAY, &v);

    uint32_t *frame = malloc((size_t)v.xres * v.yres * 4);
    uint32_t color[256] = {0};
    for (size_t i = 0; i < sizeof palette / sizeof palette[0]; i++)
        color[(unsigned char)palette[i].code] = pack(&v, palette[i].r, palette[i].g, palette[i].b);

    int js = open("/dev/input/js0", O_RDONLY | O_NONBLOCK);
    printf("joystick: %s\n", js >= 0 ? "opened" : "not available");
    int mx = v.xres / 2, my = v.yres / 2, ax = 0, ay = 0;
    time_t start = time(NULL);
    for (;;) {
        struct js_event e;
        while (js >= 0 && read(js, &e, sizeof e) == sizeof e) {
            int type = e.type & ~JS_EVENT_INIT;
            if (type == JS_EVENT_AXIS) {
                if (e.number == 0 || e.number == 2) ax = e.value;
                if (e.number == 1 || e.number == 3) ay = e.value;
            } else if (type == JS_EVENT_BUTTON && e.value == 1 && !(e.type & JS_EVENT_INIT) && time(NULL) - start >= 1) {
                printf("button %d pressed, quitting\n", e.number);
                return 0;
            }
        }
        if (time(NULL) - start > 25) { printf("timeout, quitting\n"); return 0; }
        mx += ax * 8 / 32767; my += ay * 8 / 32767;
        if (mx < 0) mx = 0;
        if (my < 0) my = 0;
        if (mx > (int)v.xres - 1) mx = v.xres - 1;
        if (my > (int)v.yres - 1) my = v.yres - 1;

        for (unsigned y = 0; y < v.yres; y++)
            for (unsigned x = 0; x < v.xres; x++)
                frame[y * v.xres + x] = color[(unsigned char)grid[y * GRID_H / v.yres][x * GRID_W / v.xres]];
        for (int dy = -12; dy <= 12; dy++)          /* white marker with a dark middle */
            for (int dx = -12; dx <= 12; dx++) {
                int x = mx + dx, y = my + dy;
                if (x < 0 || y < 0 || x >= (int)v.xres || y >= (int)v.yres) continue;
                int edge = (dx < -9 || dx > 9 || dy < -9 || dy > 9);
                frame[y * v.xres + x] = edge ? pack(&v, 255, 255, 255) : pack(&v, 230, 57, 70);
            }
        for (unsigned y = 0; y < v.yres; y++)
            memcpy(mem + (size_t)y * f.line_length, frame + (size_t)y * v.xres, (size_t)v.xres * 4);
        usleep(16000);
    }
}
