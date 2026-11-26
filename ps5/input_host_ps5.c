/*
 * ps5/input_host_ps5.c
 *
 * PS5 keyboard/mouse host shim replacing runtime/input_sdl.c.
 * On PS5, primary input comes through DualSense (ps5/sdl3_ps5.c -> runtime/input.c),
 * so the desktop keyboard/mouse helpers report focused window + no KB/mouse input.
 */

#include "input_wsys.h"
#include <stdint.h>

int ikb_foreground(void) { return 1; }
int ikb_down(int key) { (void)key; return 0; }
int ikb_escape(void) { return 0; }
int ikb_pointer(float *nx, float *ny) { (void)nx; (void)ny; return 0; }
void ikb_pointer_set(float nx, float ny) { (void)nx; (void)ny; }
int ikb_captured(void) { return 0; }
void ikb_mouse_take(int32_t *dx, int32_t *dy) {
    if (dx) *dx = 0;
    if (dy) *dy = 0;
}
uint32_t ikb_mouse_travel(void) { return 0; }
int32_t ikb_wheel_take(void) { return 0; }
void ikb_cursor_update(void) {}
void ikb_menu_closed(void) {}
uint32_t input_key_char(int key) { (void)key; return 0; }
void input_cursor_suspend(int on) { (void)on; }
int input_flight_key(void) { return 0; }
int input_cursor_released(void) { return 0; }
