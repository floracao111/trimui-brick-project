/* Stretch a Sketch, stage 2: draw with the stick, send the line to the node, show the pixel art that comes back.
 * Straight to /dev/fb0 and /dev/input/js0, so it needs no libraries (it is built static).
 *   A (right face button)  first press: put the pen down at the blue pointer. Second press: send the drawing.
 *   B (bottom face button) clear (after the art is shown, A or B starts a new drawing)
 *   hold L1 and R1 together for 1.5 seconds to quit
 * Sticks: left stick = axes 0,1; right stick = axes 3,4; D-pad = axes 6,7. Axes 2 and 5 are the L2/R2 triggers,
 * which rest at -32767, so they must never move the pointer.
 * The border shows the mode: blue = choose a start point, red = drawing, purple = waiting for the node, orange = error.
 * Sending is done by send.sh (curl): it writes points.json's reply into grid.txt and its progress into state.txt.
 * The server address and token live in server.conf, so they can change without rebuilding. */
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/joystick.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define MAX_POINTS 4500
#define MIN_STEP 3.0f
#define SPEED 144.0f       /* screen pixels per second: the simulator's 90 on a 640 wide pad, scaled to 1024 */
#define DEAD 0.15f
/* js button numbers, from the kernel's order of this pad's buttons: south, east, north, west, L1, R1, select, start */
#define BTN_PEN 1
#define BTN_CLEAR 0
#define BTN_L1 4
#define BTN_R1 5

static struct fb_var_screeninfo v;
static uint32_t *paper, *frame, *shown;
static unsigned W, H;

static uint32_t pack(int r, int g, int b) {
    return ((uint32_t)r >> (8 - v.red.length) << v.red.offset) |
           ((uint32_t)g >> (8 - v.green.length) << v.green.offset) |
           ((uint32_t)b >> (8 - v.blue.length) << v.blue.offset) |
           (v.transp.length ? (0xFFu >> (8 - v.transp.length) << v.transp.offset) : 0);
}

static double now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}

static void disc(uint32_t *buf, float cx, float cy, float r, uint32_t c) {
    int x0 = (int)floorf(cx - r), x1 = (int)ceilf(cx + r), y0 = (int)floorf(cy - r), y1 = (int)ceilf(cy + r);
    for (int y = y0; y <= y1; y++) {
        if (y < 0 || y >= (int)H) continue;
        for (int x = x0; x <= x1; x++) {
            if (x < 0 || x >= (int)W) continue;
            float dx = x - cx, dy = y - cy;
            if (dx * dx + dy * dy <= r * r) buf[y * W + x] = c;
        }
    }
}

static void ring(uint32_t *buf, float cx, float cy, float r, float w, uint32_t c) {
    int x0 = (int)(cx - r - w), x1 = (int)(cx + r + w), y0 = (int)(cy - r - w), y1 = (int)(cy + r + w);
    for (int y = y0; y <= y1; y++) {
        if (y < 0 || y >= (int)H) continue;
        for (int x = x0; x <= x1; x++) {
            if (x < 0 || x >= (int)W) continue;
            float d = hypotf(x - cx, y - cy);
            if (fabsf(d - r) <= w / 2) buf[y * W + x] = c;
        }
    }
}

static void line(uint32_t *buf, float x0, float y0, float x1, float y1, float r, uint32_t c) {
    float len = hypotf(x1 - x0, y1 - y0);
    int n = (int)len + 1;
    for (int i = 0; i <= n; i++) disc(buf, x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, r, c);
}

static void border(uint32_t *buf, int w, uint32_t c) {
    for (unsigned y = 0; y < H; y++)
        for (unsigned x = 0; x < W; x++)
            if (x < (unsigned)w || y < (unsigned)w || x >= W - w || y >= H - w) buf[y * W + x] = c;
}

/* a stick's push (-1..1 per axis) with a round dead zone, so drift is ignored and any angle works */
static void stick(float ax, float ay, float *ox, float *oy) {
    float m = hypotf(ax, ay);
    if (m < DEAD) { *ox = *oy = 0; return; }
    float k = fminf(1.0f, (m - DEAD) / (1.0f - DEAD)) / m;
    *ox = ax * k; *oy = ay * k;
}

static float px[MAX_POINTS + 2], py[MAX_POINTS + 2];
static int npts = 0;

/* the node's art as text ("P <code> <rrggbb>" and "R <64 codes>" lines), scaled up to fill the screen */
static int load_grid(uint32_t *out) {
    FILE *f = fopen("grid.txt", "r");
    if (!f) return -1;
    uint32_t color[256] = {0};
    char row[48][96]; int nrows = 0; char text[160];
    while (fgets(text, sizeof text, f)) {
        unsigned rgb;
        if (text[0] == 'P' && text[1] == ' ' && text[2] && sscanf(text + 4, "%x", &rgb) == 1)
            color[(unsigned char)text[2]] = pack(rgb >> 16, (rgb >> 8) & 255, rgb & 255);
        else if (text[0] == 'R' && text[1] == ' ' && nrows < 48 && strlen(text + 2) >= 64) {
            memcpy(row[nrows], text + 2, 64); nrows++;
        }
    }
    fclose(f);
    if (nrows != 48) return -1;
    for (unsigned y = 0; y < H; y++)
        for (unsigned x = 0; x < W; x++)
            out[y * W + x] = color[(unsigned char)row[y * 48 / H][x * 64 / W]];
    return 0;
}

static void read_state(char *buf, size_t n) {
    buf[0] = 0;
    FILE *f = fopen("state.txt", "r");
    if (!f) return;
    if (fgets(buf, n, f)) buf[strcspn(buf, "\r\n")] = 0;
    fclose(f);
}

static int save_points(void) {
    FILE *f = fopen("points.json", "w");
    if (!f) return -1;
    fputs("{\"points\":[", f);
    for (int i = 0; i < npts; i++) fprintf(f, "%s[%.4f,%.4f]", i ? "," : "", px[i] / W, py[i] / H);
    fputs("]}\n", f);
    fclose(f);
    return 0;
}

int main(void) {
    int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) { perror("open /dev/fb0"); return 1; }
    struct fb_fix_screeninfo f;
    if (ioctl(fb, FBIOGET_VSCREENINFO, &v) || ioctl(fb, FBIOGET_FSCREENINFO, &f)) { perror("fb info"); return 1; }
    if (v.bits_per_pixel != 32) { fprintf(stderr, "expected 32 bits per pixel\n"); return 1; }
    W = v.xres; H = v.yres;
    size_t size = (size_t)f.line_length * v.yres_virtual;
    uint8_t *mem = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fb, 0);
    if (mem == MAP_FAILED) { perror("mmap"); return 1; }
    v.yoffset = 0; ioctl(fb, FBIOPAN_DISPLAY, &v);
    printf("screen %ux%u\n", W, H);

    paper = malloc((size_t)W * H * 4); frame = malloc((size_t)W * H * 4); shown = malloc((size_t)W * H * 4);
    uint32_t cPaper = pack(245, 243, 235), cInk = pack(43, 43, 43), cWhite = pack(255, 255, 255);
    uint32_t cBlue = pack(31, 143, 255), cRed = pack(255, 46, 99), cPurple = pack(138, 63, 252), cOrange = pack(255, 138, 31);
    for (size_t i = 0; i < (size_t)W * H; i++) paper[i] = cPaper;

    int js = open("/dev/input/js0", O_RDONLY | O_NONBLOCK);
    printf("joystick: %s\n", js >= 0 ? "opened" : "not available");
    fflush(stdout);

    float x = W / 2, y = H / 2, aimx = 0, aimy = 0;
    int penDown = 0, axis[16] = {0}, held[16] = {0};
    unsigned axesSeen = 0, buttonsSeen = 0;
    enum { DRAWING, SENDING, SHOWING } phase = DRAWING;
    char state[160] = "", lastState[160] = "";
    double last = now(), start = last, flashUntil = 0, comboSince = 0, sentAt = 0, polledAt = 0;

    for (;;) {
        double t = now();
        float dt = (float)(t - last); if (dt > 0.05f) dt = 0.05f;
        last = t;

        struct js_event e;
        while (js >= 0 && read(js, &e, sizeof e) == sizeof e) {
            int type = e.type & ~JS_EVENT_INIT, init = e.type & JS_EVENT_INIT;
            if (type == JS_EVENT_AXIS && e.number < 16) {
                if (!(axesSeen & (1u << e.number))) { axesSeen |= 1u << e.number; printf("axis %d seen (value %d)\n", e.number, e.value); fflush(stdout); }
                axis[e.number] = e.value;
            } else if (type == JS_EVENT_BUTTON && e.number < 16) {
                held[e.number] = e.value;
                if (init || e.value != 1) continue;
                if (!(buttonsSeen & (1u << e.number))) { buttonsSeen |= 1u << e.number; }
                printf("button %d pressed\n", e.number); fflush(stdout);
                if (t - start < 1) continue;
                if (phase == SHOWING && (e.number == BTN_PEN || e.number == BTN_CLEAR)) {
                    for (size_t i = 0; i < (size_t)W * H; i++) paper[i] = cPaper;
                    penDown = 0; npts = 0; phase = DRAWING;
                    printf("new drawing\n");
                } else if (phase == DRAWING && e.number == BTN_PEN && !penDown) {
                    penDown = 1; npts = 0; px[npts] = x; py[npts] = y; npts++;
                    printf("pen down at %.0f,%.0f\n", x, y);
                } else if (phase == DRAWING && e.number == BTN_PEN && penDown && npts >= 20) {
                    px[npts] = x; py[npts] = y; npts++;
                    if (save_points()) { printf("could not write points.json\n"); }
                    else {
                        remove("grid.txt");
                        FILE *sf = fopen("state.txt", "w"); if (sf) { fputs("sending\n", sf); fclose(sf); }
                        if (system("sh ./send.sh > send.log 2>&1 &") != 0) printf("could not start send.sh\n");
                        phase = SENDING; sentAt = t; lastState[0] = 0;
                        printf("sending %d points\n", npts);
                    }
                } else if (phase == DRAWING && e.number == BTN_CLEAR) {
                    for (size_t i = 0; i < (size_t)W * H; i++) paper[i] = cPaper;
                    penDown = 0; npts = 0;
                    printf("cleared\n");
                }
                fflush(stdout);
            }
        }
        if (held[BTN_L1] && held[BTN_R1]) { if (!comboSince) comboSince = t; else if (t - comboSince > 1.5) { printf("combo: quitting\n"); return 0; } }
        else comboSince = 0;
        if (t - start > 1200) { printf("20 minute limit, quitting\n"); return 0; }

        if (phase == SENDING && t - polledAt > 0.5) {
            polledAt = t;
            read_state(state, sizeof state);
            if (strcmp(state, lastState)) { printf("state: %s\n", state); fflush(stdout); strcpy(lastState, state); }
            if (!strncmp(state, "done", 4)) {
                if (load_grid(shown) == 0) { phase = SHOWING; printf("showing the art after %.0f s\n", t - sentAt); }
                else { printf("grid.txt was not readable\n"); phase = DRAWING; flashUntil = t + 3; }
                fflush(stdout);
            } else if (!strncmp(state, "error", 5)) { phase = DRAWING; flashUntil = t + 3; }
        }

        /* both sticks and the D-pad add together, and a diagonal is no faster than a straight line */
        float lx, ly, rx, ry, hx, hy;
        stick(axis[0] / 32767.0f, axis[1] / 32767.0f, &lx, &ly);
        stick(axis[3] / 32767.0f, axis[4] / 32767.0f, &rx, &ry);
        stick(axis[6] / 32767.0f, axis[7] / 32767.0f, &hx, &hy);
        float dx = lx + rx + hx, dy = ly + ry + hy, m = hypotf(dx, dy);
        if (m > 1) { dx /= m; dy /= m; }
        aimx = aimy = 0;
        if (phase == DRAWING && (dx || dy) && (!penDown || npts < MAX_POINTS)) {
            aimx = dx; aimy = dy;
            float nx = fminf(fmaxf(x + dx * SPEED * dt, 0), W - 1), ny = fminf(fmaxf(y + dy * SPEED * dt, 0), H - 1);
            if (penDown) line(paper, x, y, nx, ny, 3.0f, cInk);
            x = nx; y = ny;
            if (penDown && hypotf(x - px[npts - 1], y - py[npts - 1]) >= MIN_STEP) { px[npts] = x; py[npts] = y; npts++; }
        }

        if (phase == SHOWING) {
            for (unsigned row = 0; row < H; row++)
                memcpy(mem + (size_t)row * f.line_length, shown + (size_t)row * W, (size_t)W * 4);
            usleep(30000);
            continue;
        }
        memcpy(frame, paper, (size_t)W * H * 4);
        uint32_t mode = t < flashUntil ? cOrange : phase == SENDING ? cPurple : penDown ? cRed : cBlue;
        float pulse = 1.0f + 0.15f * sinf((float)(t * 6.5));
        for (int pass = 0; pass < 2; pass++) {        /* white outline first, then the colour on top */
            uint32_t c = pass ? mode : cWhite;
            float w = pass ? 4 : 9, arm = pass ? 0 : 3;
            ring(frame, x, y, 14 * pulse, w, c);
            for (int s = -1; s <= 1; s += 2) {
                line(frame, x + s * 8, y, x + s * 28, y, w / 2 + arm / 2, c);
                line(frame, x, y + s * 8, x, y + s * 28, w / 2 + arm / 2, c);
            }
            if (aimx || aimy) {
                float len = hypotf(aimx, aimy), ux = aimx / len, uy = aimy / len;
                float ex = x + ux * 64, ey = y + uy * 64;
                line(frame, x + ux * 32, y + uy * 32, ex, ey, w / 2, c);
                line(frame, ex, ey, ex - ux * 16 - uy * 10, ey - uy * 16 + ux * 10, w / 2, c);
                line(frame, ex, ey, ex - ux * 16 + uy * 10, ey - uy * 16 - ux * 10, w / 2, c);
            }
        }
        border(frame, 8, mode);
        if (phase == SENDING) {                         /* a block sweeping along the bottom while the node works */
            int bx = (int)fmod(t * 320, W + 240) - 240;
            for (unsigned yy = H - 40; yy < H - 20; yy++)
                for (int xx = bx; xx < bx + 240; xx++)
                    if (xx >= 0 && xx < (int)W) frame[yy * W + xx] = cPurple;
        }

        for (unsigned row = 0; row < H; row++)
            memcpy(mem + (size_t)row * f.line_length, frame + (size_t)row * W, (size_t)W * 4);
        usleep(10000);
    }
}
