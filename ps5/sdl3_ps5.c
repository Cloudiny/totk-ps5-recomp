/*
 * ps5/sdl3_ps5.c
 *
 * PS5-native SDL3 shim for TOTK's runtime/audio_mixer.c and runtime/input.c.
 * Routes:
 *   - SDL3 AudioStream (F32 48kHz) -> libSceAudioOut (S16 stereo 48kHz) on a pull thread
 *   - SDL3 Gamepad / Sensors / Rumble -> libSceUserService + libScePad (DualSense)
 */

#include <SDL3/SDL.h>
#include "plat_ps5.h"

#include <math.h>
#include <pthread.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* Sony PS5 libSceUserService / libScePad / libSceAudioOut symbols (in exported.txt) */
extern int32_t sceUserServiceInitialize(const void *params);
extern int32_t sceUserServiceGetInitialUser(int32_t *user_id);
extern int32_t scePadInit(void);
extern int32_t scePadOpen(int32_t user_id, int32_t type, int32_t index, const void *param);
extern int32_t scePadClose(int32_t handle);
extern int32_t scePadReadState(int32_t handle, void *data);
extern int32_t scePadSetVibration(int32_t handle, const void *param);
extern int32_t scePadSetMotionSensorState(int32_t handle, bool enable);

extern int32_t sceAudioOutInit(void);
extern int32_t sceAudioOutOpen(
    int32_t user_id, int32_t type, int32_t index, uint32_t len, uint32_t freq, uint32_t param);
extern int32_t sceAudioOutOutput(int32_t handle, const void *ptr);
extern int32_t sceAudioOutClose(int32_t handle);
extern int32_t sceKernelUsleep(uint32_t microseconds);
extern void rt_log(const char *fmt, ...);

/* Standard PS4/PS5 ScePadData binary layout (OpenOrbis / libScePad ABI:
 * orientation @ 0x0C, acceleration @ 0x1C, angularVelocity @ 0x28, touchData @ 0x34, connected @ 0x4C). */
typedef struct Ps5PadVec3 { float x, y, z; } Ps5PadVec3;
typedef struct Ps5PadQuat { float x, y, z, w; } Ps5PadQuat;
typedef struct Ps5PadData {
    uint32_t buttons;
    uint8_t lx, ly, rx, ry;
    uint8_t l2, r2;
    uint8_t pad0[2];
    Ps5PadQuat orientation;
    Ps5PadVec3 acceleration;
    Ps5PadVec3 angular_velocity;
    uint8_t touch_data[24];
    uint8_t connected;
    uint8_t reserved[64];
} Ps5PadData;

_Static_assert(offsetof(Ps5PadData, orientation) == 0x0C, "ScePadData.orientation must sit at 0x0C");
_Static_assert(offsetof(Ps5PadData, acceleration) == 0x1C, "ScePadData.acceleration must sit at 0x1C");
_Static_assert(offsetof(Ps5PadData, angular_velocity) == 0x28, "ScePadData.angularVelocity must sit at 0x28");
_Static_assert(offsetof(Ps5PadData, touch_data) == 0x34, "ScePadData.touchData must sit at 0x34");
_Static_assert(offsetof(Ps5PadData, connected) == 0x4C, "ScePadData.connected must sit at 0x4C");

typedef struct Ps5PadVibration {
    uint8_t large_motor;
    uint8_t small_motor;
} Ps5PadVibration;

/* PS4/PS5 ScePadButtonDataOffset bit masks */
enum {
    PS5_BTN_L3       = 0x00000002u,
    PS5_BTN_R3       = 0x00000004u,
    PS5_BTN_OPTIONS  = 0x00000008u,
    PS5_BTN_UP       = 0x00000010u,
    PS5_BTN_RIGHT    = 0x00000020u,
    PS5_BTN_DOWN     = 0x00000040u,
    PS5_BTN_LEFT     = 0x00000080u,
    PS5_BTN_L2       = 0x00000100u,
    PS5_BTN_R2       = 0x00000200u,
    PS5_BTN_L1       = 0x00000400u,
    PS5_BTN_R1       = 0x00000800u,
    PS5_BTN_TRIANGLE = 0x00001000u,
    PS5_BTN_CIRCLE   = 0x00002000u,
    PS5_BTN_CROSS    = 0x00004000u,
    PS5_BTN_SQUARE   = 0x00008000u,
    PS5_BTN_TOUCHPAD = 0x00100000u,
    PS5_BTN_CREATE   = 0x00000001u,
};

static Uint32 g_sdl_inited = 0;

bool SDL_Init(Uint32 flags) {
    return SDL_InitSubSystem(flags);
}

bool SDL_InitSubSystem(Uint32 flags) {
    if (flags & SDL_INIT_AUDIO) {
        sceAudioOutInit();
    }
    if (flags & SDL_INIT_GAMEPAD) {
        sceUserServiceInitialize(NULL);
        scePadInit();
    }
    g_sdl_inited |= flags;
    return true;
}

void SDL_QuitSubSystem(Uint32 flags) {
    g_sdl_inited &= ~flags;
}

Uint32 SDL_WasInit(Uint32 flags) {
    return flags ? (g_sdl_inited & flags) : g_sdl_inited;
}

const char *SDL_GetError(void) { return ""; }
void SDL_free(void *mem) { free(mem); }
bool SDL_SetHint(const char *name, const char *value) { (void)name; (void)value; return true; }
bool SDL_SetHintWithPriority(const char *name, const char *value, SDL_HintPriority p) {
    (void)name; (void)value; (void)p; return true;
}
void SDL_SetEventEnabled(Uint32 type, bool enabled) { (void)type; (void)enabled; }

/* ---- Audio Stream -> libSceAudioOut ---- */
#define PS5_AUDIO_GRAIN 256u

struct SDL_AudioStream {
    SDL_AudioDeviceID devid;
    SDL_AudioSpec spec;
    SDL_AudioStreamCallback callback;
    void *userdata;
    int32_t sce_handle;
    volatile int running;
    volatile int stop;
    pthread_t thread;
    int has_thread;
    float f32_buf[PS5_AUDIO_GRAIN * 6];
    int f32_queued_bytes;
    int16_t s16_buf[PS5_AUDIO_GRAIN * 2];
};

static int16_t f32_to_s16(float x) {
    if (x > 1.0f) x = 1.0f;
    else if (x < -1.0f) x = -1.0f;
    return (int16_t)(x * 32767.0f);
}

static void *ps5_audio_thread(void *arg) {
    SDL_AudioStream *s = (SDL_AudioStream *)arg;
    const int ch = s->spec.channels > 0 ? s->spec.channels : 2;
    const int need_bytes = (int)(PS5_AUDIO_GRAIN * (uint32_t)ch * sizeof(float));

    while (!s->stop) {
        if (!s->running) {
            sceKernelUsleep(2000);
            continue;
        }
        s->f32_queued_bytes = 0;
        memset(s->f32_buf, 0, (size_t)need_bytes);
        if (s->callback) {
            s->callback(s->userdata, s, need_bytes, need_bytes);
        }
        /* Downmix 2ch or 6ch F32 -> stereo S16 for libSceAudioOut */
        for (uint32_t i = 0; i < PS5_AUDIO_GRAIN; ++i) {
            float l = 0.0f, r = 0.0f;
            if (ch >= 6) {
                const float *f = &s->f32_buf[i * 6];
                l = f[0] + 0.707f * f[2] + 0.5f * f[4];
                r = f[1] + 0.707f * f[2] + 0.5f * f[5];
            } else if (ch >= 2) {
                l = s->f32_buf[i * 2];
                r = s->f32_buf[i * 2 + 1];
            } else {
                l = r = s->f32_buf[i];
            }
            s->s16_buf[i * 2] = f32_to_s16(l);
            s->s16_buf[i * 2 + 1] = f32_to_s16(r);
        }
        if (s->sce_handle >= 0) {
            sceAudioOutOutput(s->sce_handle, s->s16_buf);
        } else {
            sceKernelUsleep(5333);
        }
    }
    return NULL;
}

SDL_AudioDeviceID *SDL_GetAudioPlaybackDevices(int *count) {
    SDL_AudioDeviceID *ids = (SDL_AudioDeviceID *)malloc(sizeof(SDL_AudioDeviceID) * 2);
    if (!ids) {
        if (count) *count = 0;
        return NULL;
    }
    ids[0] = 1;
    ids[1] = 0;
    if (count) *count = 1;
    return ids;
}

const char *SDL_GetAudioDeviceName(SDL_AudioDeviceID devid) {
    (void)devid;
    return "PS5 HDMI AudioOut";
}

bool SDL_GetAudioDeviceFormat(SDL_AudioDeviceID devid, SDL_AudioSpec *spec, int *sample_frames) {
    (void)devid;
    if (spec) {
        spec->format = SDL_AUDIO_F32;
        spec->channels = 2;
        spec->freq = 48000;
    }
    if (sample_frames) {
        *sample_frames = (int)PS5_AUDIO_GRAIN;
    }
    return true;
}

SDL_AudioStream *SDL_OpenAudioDeviceStream(
    SDL_AudioDeviceID devid,
    const SDL_AudioSpec *spec,
    SDL_AudioStreamCallback callback,
    void *userdata
) {
    SDL_AudioStream *s = (SDL_AudioStream *)calloc(1, sizeof(*s));
    if (!s) return NULL;
    s->devid = devid ? devid : 1;
    if (spec) {
        s->spec = *spec;
    } else {
        s->spec.format = SDL_AUDIO_F32;
        s->spec.channels = 2;
        s->spec.freq = 48000;
    }
    s->callback = callback;
    s->userdata = userdata;
    sceAudioOutInit();
    s->sce_handle = sceAudioOutOpen(0xFF, 0, 0, PS5_AUDIO_GRAIN, 48000u, 1u);
    rt_log("ps5-sdl: audio open handle=%d ch=%d freq=%d", s->sce_handle, s->spec.channels, s->spec.freq);
    if (pthread_create(&s->thread, NULL, ps5_audio_thread, s) == 0) {
        s->has_thread = 1;
    }
    return s;
}

SDL_AudioDeviceID SDL_GetAudioStreamDevice(SDL_AudioStream *stream) {
    return stream ? stream->devid : 0;
}

bool SDL_PutAudioStreamData(SDL_AudioStream *stream, const void *buf, int len) {
    if (!stream || !buf || len <= 0) return false;
    int cap = (int)sizeof(stream->f32_buf) - stream->f32_queued_bytes;
    int copy = len < cap ? len : cap;
    if (copy > 0) {
        memcpy(((uint8_t *)stream->f32_buf) + stream->f32_queued_bytes, buf, (size_t)copy);
        stream->f32_queued_bytes += copy;
    }
    return true;
}

bool SDL_ResumeAudioStreamDevice(SDL_AudioStream *stream) {
    if (!stream) return false;
    stream->running = 1;
    return true;
}

void SDL_DestroyAudioStream(SDL_AudioStream *stream) {
    if (!stream) return;
    stream->stop = 1;
    if (stream->has_thread) {
        pthread_join(stream->thread, NULL);
    }
    if (stream->sce_handle >= 0) {
        sceAudioOutClose(stream->sce_handle);
    }
    free(stream);
}

/* ---- Gamepad -> DualSense libScePad ---- */
struct SDL_Gamepad {
    SDL_JoystickID id;
    int32_t handle;
    Ps5PadData state;
    bool connected;
    bool motion_enabled;
};

static struct SDL_Gamepad g_dualsense = { .id = 1, .handle = -1 };

static int16_t u8_axis_to_s16(uint8_t v) {
    int32_t s = ((int32_t)v - 128) * 256;
    if (s < -32768) s = -32768;
    if (s > 32767) s = 32767;
    return (int16_t)s;
}

void SDL_UpdateGamepads(void) {
    if (g_dualsense.handle >= 0) {
        Ps5PadData data;
        memset(&data, 0, sizeof(data));
        if (scePadReadState(g_dualsense.handle, &data) == 0) {
            g_dualsense.state = data;
            g_dualsense.connected = data.connected != 0;
        }
    }
}

SDL_JoystickID *SDL_GetGamepads(int *count) {
    SDL_JoystickID *ids = (SDL_JoystickID *)malloc(sizeof(SDL_JoystickID) * 2);
    if (!ids) {
        if (count) *count = 0;
        return NULL;
    }
    ids[0] = 1;
    ids[1] = 0;
    if (count) *count = 1;
    return ids;
}

SDL_Gamepad *SDL_OpenGamepad(SDL_JoystickID instance_id) {
    if (instance_id != 1) return NULL;
    if (g_dualsense.handle < 0) {
        int32_t uid = -1;
        sceUserServiceInitialize(NULL);
        int32_t urc = sceUserServiceGetInitialUser(&uid);
        if (urc >= 0) {
            scePadInit();
            g_dualsense.handle = scePadOpen(uid, 0, 0, NULL);
        }
        rt_log("ps5-sdl: gamepad open urc=%#x uid=%d handle=%#x", (unsigned)urc, uid, (unsigned)g_dualsense.handle);
    }
    g_dualsense.connected = (g_dualsense.handle >= 0);
    return &g_dualsense;
}

void SDL_CloseGamepad(SDL_Gamepad *gamepad) {
    (void)gamepad;
}

bool SDL_GamepadConnected(SDL_Gamepad *gamepad) {
    return gamepad ? gamepad->connected : false;
}

SDL_JoystickID SDL_GetGamepadID(SDL_Gamepad *gamepad) {
    return gamepad ? gamepad->id : 0;
}

const char *SDL_GetGamepadName(SDL_Gamepad *gamepad) {
    (void)gamepad;
    return "DualSense Wireless Controller";
}

Uint16 SDL_GetGamepadVendor(SDL_Gamepad *gamepad) { (void)gamepad; return 0x054Cu; }
Uint16 SDL_GetGamepadProduct(SDL_Gamepad *gamepad) { (void)gamepad; return 0x0CE6u; }
Uint16 SDL_GetGamepadVendorForID(SDL_JoystickID id) { (void)id; return 0x054Cu; }
const char *SDL_GetGamepadSerial(SDL_Gamepad *gamepad) { (void)gamepad; return "PS5-PAD0"; }

SDL_GUID SDL_GetGamepadGUIDForID(SDL_JoystickID id) {
    (void)id;
    SDL_GUID g;
    memset(&g, 0, sizeof(g));
    return g;
}

void SDL_GetJoystickGUIDInfo(SDL_GUID guid, Uint16 *vendor, Uint16 *product, Uint16 *version, Uint16 *crc16) {
    (void)guid;
    if (vendor) *vendor = 0x054Cu;
    if (product) *product = 0x0CE6u;
    if (version) *version = 1;
    if (crc16) *crc16 = 0;
}

bool SDL_IsJoystickSteamVirtualGamepad(Uint16 v, Uint16 p, Uint16 c) {
    (void)v; (void)p; (void)c; return false;
}

SDL_PropertiesID SDL_GetGamepadProperties(SDL_Gamepad *gamepad) { return gamepad ? 1u : 0u; }
bool SDL_GetBooleanProperty(SDL_PropertiesID props, const char *name, bool default_value) {
    (void)props;
    if (name && strcmp(name, SDL_PROP_GAMEPAD_CAP_RUMBLE_BOOLEAN) == 0) return true;
    return default_value;
}

bool SDL_GetGamepadButton(SDL_Gamepad *gamepad, SDL_GamepadButton button) {
    if (!gamepad) return false;
    uint32_t b = gamepad->state.buttons;
    switch (button) {
    case SDL_GAMEPAD_BUTTON_SOUTH:          return (b & PS5_BTN_CROSS) != 0;
    case SDL_GAMEPAD_BUTTON_EAST:           return (b & PS5_BTN_CIRCLE) != 0;
    case SDL_GAMEPAD_BUTTON_WEST:           return (b & PS5_BTN_SQUARE) != 0;
    case SDL_GAMEPAD_BUTTON_NORTH:          return (b & PS5_BTN_TRIANGLE) != 0;
    case SDL_GAMEPAD_BUTTON_BACK:           return (b & (PS5_BTN_CREATE | PS5_BTN_TOUCHPAD)) != 0;
    case SDL_GAMEPAD_BUTTON_START:          return (b & PS5_BTN_OPTIONS) != 0;
    case SDL_GAMEPAD_BUTTON_LEFT_STICK:     return (b & PS5_BTN_L3) != 0;
    case SDL_GAMEPAD_BUTTON_RIGHT_STICK:    return (b & PS5_BTN_R3) != 0;
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER:  return (b & PS5_BTN_L1) != 0;
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return (b & PS5_BTN_R1) != 0;
    case SDL_GAMEPAD_BUTTON_DPAD_UP:        return (b & PS5_BTN_UP) != 0;
    case SDL_GAMEPAD_BUTTON_DPAD_DOWN:      return (b & PS5_BTN_DOWN) != 0;
    case SDL_GAMEPAD_BUTTON_DPAD_LEFT:      return (b & PS5_BTN_LEFT) != 0;
    case SDL_GAMEPAD_BUTTON_DPAD_RIGHT:     return (b & PS5_BTN_RIGHT) != 0;
    case SDL_GAMEPAD_BUTTON_TOUCHPAD:       return (b & PS5_BTN_TOUCHPAD) != 0;
    default: return false;
    }
}

Sint16 SDL_GetGamepadAxis(SDL_Gamepad *gamepad, SDL_GamepadAxis axis) {
    if (!gamepad) return 0;
    switch (axis) {
    case SDL_GAMEPAD_AXIS_LEFTX:         return u8_axis_to_s16(gamepad->state.lx);
    case SDL_GAMEPAD_AXIS_LEFTY:         return u8_axis_to_s16(gamepad->state.ly);
    case SDL_GAMEPAD_AXIS_RIGHTX:        return u8_axis_to_s16(gamepad->state.rx);
    case SDL_GAMEPAD_AXIS_RIGHTY:        return u8_axis_to_s16(gamepad->state.ry);
    case SDL_GAMEPAD_AXIS_LEFT_TRIGGER:  return (Sint16)((int32_t)gamepad->state.l2 * 128);
    case SDL_GAMEPAD_AXIS_RIGHT_TRIGGER: return (Sint16)((int32_t)gamepad->state.r2 * 128);
    default: return 0;
    }
}

SDL_GamepadButtonLabel SDL_GetGamepadButtonLabel(SDL_Gamepad *gamepad, SDL_GamepadButton button) {
    (void)gamepad;
    switch (button) {
    case SDL_GAMEPAD_BUTTON_SOUTH: return SDL_GAMEPAD_BUTTON_LABEL_CROSS;
    case SDL_GAMEPAD_BUTTON_EAST:  return SDL_GAMEPAD_BUTTON_LABEL_CIRCLE;
    case SDL_GAMEPAD_BUTTON_WEST:  return SDL_GAMEPAD_BUTTON_LABEL_SQUARE;
    case SDL_GAMEPAD_BUTTON_NORTH: return SDL_GAMEPAD_BUTTON_LABEL_TRIANGLE;
    default: return SDL_GAMEPAD_BUTTON_LABEL_UNKNOWN;
    }
}

bool SDL_GamepadHasSensor(SDL_Gamepad *gamepad, SDL_SensorType type) {
    (void)gamepad;
    return type == SDL_SENSOR_ACCEL || type == SDL_SENSOR_GYRO;
}

bool SDL_SetGamepadSensorEnabled(SDL_Gamepad *gamepad, SDL_SensorType type, bool enabled) {
    (void)type;
    if (!gamepad || gamepad->handle < 0) return false;
    gamepad->motion_enabled = enabled;
    return scePadSetMotionSensorState(gamepad->handle, enabled) == 0;
}

float SDL_GetGamepadSensorDataRate(SDL_Gamepad *gamepad, SDL_SensorType type) {
    (void)gamepad; (void)type;
    return 250.0f;
}

bool SDL_GetGamepadSensorData(SDL_Gamepad *gamepad, SDL_SensorType type, float *data, int num_values) {
    if (!gamepad || !data || num_values < 3) return false;
    if (type == SDL_SENSOR_ACCEL) {
        data[0] = gamepad->state.acceleration.x * SDL_STANDARD_GRAVITY;
        data[1] = gamepad->state.acceleration.y * SDL_STANDARD_GRAVITY;
        data[2] = gamepad->state.acceleration.z * SDL_STANDARD_GRAVITY;
        return true;
    }
    if (type == SDL_SENSOR_GYRO) {
        data[0] = gamepad->state.angular_velocity.x;
        data[1] = gamepad->state.angular_velocity.y;
        data[2] = gamepad->state.angular_velocity.z;
        return true;
    }
    return false;
}

bool SDL_RumbleGamepad(SDL_Gamepad *gamepad, Uint16 low_freq, Uint16 high_freq, Uint32 duration_ms) {
    (void)duration_ms;
    if (!gamepad || gamepad->handle < 0) return false;
    Ps5PadVibration vib;
    vib.large_motor = (uint8_t)(low_freq >> 8);
    vib.small_motor = (uint8_t)(high_freq >> 8);
    return scePadSetVibration(gamepad->handle, &vib) == 0;
}

bool SDL_RumbleGamepadTriggers(SDL_Gamepad *gamepad, Uint16 l, Uint16 r, Uint32 d) {
    (void)gamepad; (void)l; (void)r; (void)d;
    return false;
}

SDL_JoystickID SDL_AttachVirtualJoystick(const SDL_VirtualJoystickDesc *desc) { (void)desc; return 0; }
SDL_Joystick *SDL_OpenJoystick(SDL_JoystickID id) { (void)id; return NULL; }
bool SDL_SetJoystickVirtualAxis(SDL_Joystick *j, int axis, Sint16 val) {
    (void)j; (void)axis; (void)val; return false;
}
