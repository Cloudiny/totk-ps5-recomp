/*
 * third_party/ps5_compat_inc/SDL3/SDL.h
 *
 * Lightweight PS5-native SDL3 subset header allowing TOTK's runtime/audio_mixer.c
 * and runtime/input.c to compile unmodified on x86_64-sie-ps5, backed by
 * ps5/sdl3_ps5.c (libScePad DualSense + libSceAudioOut 48 kHz PCM).
 */

#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int16_t Sint16;
typedef uint16_t Uint16;
typedef uint32_t Uint32;
typedef uint64_t Uint64;
typedef uint8_t Uint8;

#ifndef SDLCALL
#define SDLCALL
#endif

#define SDL_INIT_AUDIO   0x00000010u
#define SDL_INIT_GAMEPAD 0x00002000u

#define SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"
#define SDL_HINT_GAMECONTROLLER_IGNORE_DEVICES    "SDL_GAMECONTROLLER_IGNORE_DEVICES"

typedef enum SDL_HintPriority {
    SDL_HINT_DEFAULT = 0,
    SDL_HINT_NORMAL = 1,
    SDL_HINT_OVERRIDE = 2,
} SDL_HintPriority;

#define SDL_STANDARD_GRAVITY 9.80665f

#define SDL_INIT_INTERFACE(iface)          \
    do {                                   \
        memset((iface), 0, sizeof(*(iface))); \
        (iface)->version = sizeof(*(iface));  \
    } while (0)

bool SDL_Init(Uint32 flags);
bool SDL_InitSubSystem(Uint32 flags);
void SDL_QuitSubSystem(Uint32 flags);
Uint32 SDL_WasInit(Uint32 flags);
const char *SDL_GetError(void);
void SDL_free(void *mem);
bool SDL_SetHint(const char *name, const char *value);
bool SDL_SetHintWithPriority(const char *name, const char *value, SDL_HintPriority priority);
void SDL_SetEventEnabled(Uint32 type, bool enabled);

/* ---- Audio ---- */
typedef Uint32 SDL_AudioDeviceID;
typedef Uint32 SDL_AudioFormat;

#define SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK ((SDL_AudioDeviceID)0xFFFFFFFFu)
#define SDL_AUDIO_F32 ((SDL_AudioFormat)0x8120u)

typedef struct SDL_AudioSpec {
    SDL_AudioFormat format;
    int channels;
    int freq;
} SDL_AudioSpec;

typedef struct SDL_AudioStream SDL_AudioStream;
typedef void (*SDL_AudioStreamCallback)(
    void *userdata,
    SDL_AudioStream *stream,
    int additional_amount,
    int total_amount
);

SDL_AudioDeviceID *SDL_GetAudioPlaybackDevices(int *count);
const char *SDL_GetAudioDeviceName(SDL_AudioDeviceID devid);
bool SDL_GetAudioDeviceFormat(SDL_AudioDeviceID devid, SDL_AudioSpec *spec, int *sample_frames);
SDL_AudioStream *SDL_OpenAudioDeviceStream(
    SDL_AudioDeviceID devid,
    const SDL_AudioSpec *spec,
    SDL_AudioStreamCallback callback,
    void *userdata
);
SDL_AudioDeviceID SDL_GetAudioStreamDevice(SDL_AudioStream *stream);
bool SDL_PutAudioStreamData(SDL_AudioStream *stream, const void *buf, int len);
bool SDL_ResumeAudioStreamDevice(SDL_AudioStream *stream);
void SDL_DestroyAudioStream(SDL_AudioStream *stream);

/* ---- Gamepad / Joystick / Sensors ---- */
typedef Uint32 SDL_JoystickID;
typedef Uint32 SDL_PropertiesID;

typedef struct SDL_GUID {
    Uint8 data[16];
} SDL_GUID;

typedef struct SDL_Gamepad SDL_Gamepad;
typedef struct SDL_Joystick SDL_Joystick;

typedef enum SDL_GamepadButton {
    SDL_GAMEPAD_BUTTON_INVALID = -1,
    SDL_GAMEPAD_BUTTON_SOUTH = 0,
    SDL_GAMEPAD_BUTTON_EAST,
    SDL_GAMEPAD_BUTTON_WEST,
    SDL_GAMEPAD_BUTTON_NORTH,
    SDL_GAMEPAD_BUTTON_BACK,
    SDL_GAMEPAD_BUTTON_GUIDE,
    SDL_GAMEPAD_BUTTON_START,
    SDL_GAMEPAD_BUTTON_LEFT_STICK,
    SDL_GAMEPAD_BUTTON_RIGHT_STICK,
    SDL_GAMEPAD_BUTTON_LEFT_SHOULDER,
    SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER,
    SDL_GAMEPAD_BUTTON_DPAD_UP,
    SDL_GAMEPAD_BUTTON_DPAD_DOWN,
    SDL_GAMEPAD_BUTTON_DPAD_LEFT,
    SDL_GAMEPAD_BUTTON_DPAD_RIGHT,
    SDL_GAMEPAD_BUTTON_MISC1,
    SDL_GAMEPAD_BUTTON_RIGHT_PADDLE1,
    SDL_GAMEPAD_BUTTON_LEFT_PADDLE1,
    SDL_GAMEPAD_BUTTON_RIGHT_PADDLE2,
    SDL_GAMEPAD_BUTTON_LEFT_PADDLE2,
    SDL_GAMEPAD_BUTTON_TOUCHPAD,
    SDL_GAMEPAD_BUTTON_COUNT,
} SDL_GamepadButton;

typedef enum SDL_GamepadButtonLabel {
    SDL_GAMEPAD_BUTTON_LABEL_UNKNOWN = 0,
    SDL_GAMEPAD_BUTTON_LABEL_A,
    SDL_GAMEPAD_BUTTON_LABEL_B,
    SDL_GAMEPAD_BUTTON_LABEL_X,
    SDL_GAMEPAD_BUTTON_LABEL_Y,
    SDL_GAMEPAD_BUTTON_LABEL_CROSS,
    SDL_GAMEPAD_BUTTON_LABEL_CIRCLE,
    SDL_GAMEPAD_BUTTON_LABEL_SQUARE,
    SDL_GAMEPAD_BUTTON_LABEL_TRIANGLE,
} SDL_GamepadButtonLabel;

typedef enum SDL_GamepadAxis {
    SDL_GAMEPAD_AXIS_INVALID = -1,
    SDL_GAMEPAD_AXIS_LEFTX = 0,
    SDL_GAMEPAD_AXIS_LEFTY,
    SDL_GAMEPAD_AXIS_RIGHTX,
    SDL_GAMEPAD_AXIS_RIGHTY,
    SDL_GAMEPAD_AXIS_LEFT_TRIGGER,
    SDL_GAMEPAD_AXIS_RIGHT_TRIGGER,
    SDL_GAMEPAD_AXIS_COUNT,
} SDL_GamepadAxis;

typedef enum SDL_SensorType {
    SDL_SENSOR_INVALID = -1,
    SDL_SENSOR_UNKNOWN = 0,
    SDL_SENSOR_ACCEL = 1,
    SDL_SENSOR_GYRO = 2,
} SDL_SensorType;

typedef enum SDL_JoystickType {
    SDL_JOYSTICK_TYPE_UNKNOWN = 0,
    SDL_JOYSTICK_TYPE_GAMEPAD = 1,
} SDL_JoystickType;

#define SDL_EVENT_GAMEPAD_SENSOR_UPDATE 0x659u
#define SDL_PROP_GAMEPAD_CAP_RUMBLE_BOOLEAN "SDL.gamepad.cap.rumble"

typedef struct SDL_VirtualJoystickDesc {
    Uint32 version;
    Uint16 type;
    Uint16 padding;
    Uint16 vendor_id;
    Uint16 product_id;
    Uint16 naxes;
    Uint16 nbuttons;
    Uint16 nballs;
    Uint16 nhats;
    Uint16 ntouchpads;
    Uint16 nsensors;
    Uint16 padding2[2];
    Uint32 button_mask;
    Uint32 axis_mask;
    const char *name;
    void *touchpads;
    void *sensors;
    void *userdata;
    void (*Update)(void *userdata);
    void (*SetPlayerIndex)(void *userdata, int player_index);
    bool (*Rumble)(void *userdata, Uint16 low_frequency_rumble, Uint16 high_frequency_rumble);
    bool (*RumbleTriggers)(void *userdata, Uint16 left_rumble, Uint16 right_rumble);
    bool (*SetLED)(void *userdata, Uint8 red, Uint8 green, Uint8 blue);
    bool (*SendEffect)(void *userdata, const void *data, int size);
    bool (*SetSensorsEnabled)(void *userdata, bool enabled);
    void (*Cleanup)(void *userdata);
} SDL_VirtualJoystickDesc;

void SDL_UpdateGamepads(void);
SDL_JoystickID *SDL_GetGamepads(int *count);
SDL_Gamepad *SDL_OpenGamepad(SDL_JoystickID instance_id);
void SDL_CloseGamepad(SDL_Gamepad *gamepad);
bool SDL_GamepadConnected(SDL_Gamepad *gamepad);
SDL_JoystickID SDL_GetGamepadID(SDL_Gamepad *gamepad);
const char *SDL_GetGamepadName(SDL_Gamepad *gamepad);
Uint16 SDL_GetGamepadVendor(SDL_Gamepad *gamepad);
Uint16 SDL_GetGamepadProduct(SDL_Gamepad *gamepad);
Uint16 SDL_GetGamepadVendorForID(SDL_JoystickID instance_id);
const char *SDL_GetGamepadSerial(SDL_Gamepad *gamepad);
SDL_GUID SDL_GetGamepadGUIDForID(SDL_JoystickID instance_id);
void SDL_GetJoystickGUIDInfo(SDL_GUID guid, Uint16 *vendor, Uint16 *product, Uint16 *version, Uint16 *crc16);
bool SDL_IsJoystickSteamVirtualGamepad(Uint16 vendor_id, Uint16 product_id, Uint16 crc16);
SDL_PropertiesID SDL_GetGamepadProperties(SDL_Gamepad *gamepad);
bool SDL_GetBooleanProperty(SDL_PropertiesID props, const char *name, bool default_value);
bool SDL_GetGamepadButton(SDL_Gamepad *gamepad, SDL_GamepadButton button);
Sint16 SDL_GetGamepadAxis(SDL_Gamepad *gamepad, SDL_GamepadAxis axis);
SDL_GamepadButtonLabel SDL_GetGamepadButtonLabel(SDL_Gamepad *gamepad, SDL_GamepadButton button);
bool SDL_GamepadHasSensor(SDL_Gamepad *gamepad, SDL_SensorType type);
bool SDL_SetGamepadSensorEnabled(SDL_Gamepad *gamepad, SDL_SensorType type, bool enabled);
float SDL_GetGamepadSensorDataRate(SDL_Gamepad *gamepad, SDL_SensorType type);
bool SDL_GetGamepadSensorData(SDL_Gamepad *gamepad, SDL_SensorType type, float *data, int num_values);
bool SDL_RumbleGamepad(SDL_Gamepad *gamepad, Uint16 low_freq, Uint16 high_freq, Uint32 duration_ms);
bool SDL_RumbleGamepadTriggers(SDL_Gamepad *gamepad, Uint16 left_rumble, Uint16 right_rumble, Uint32 duration_ms);

SDL_JoystickID SDL_AttachVirtualJoystick(const SDL_VirtualJoystickDesc *desc);
SDL_Joystick *SDL_OpenJoystick(SDL_JoystickID instance_id);
bool SDL_SetJoystickVirtualAxis(SDL_Joystick *joystick, int axis, Sint16 value);

#ifdef __cplusplus
}
#endif
