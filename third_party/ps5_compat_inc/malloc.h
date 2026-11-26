/* PS5 FreeBSD SDK <malloc.h> raises #error telling callers to include <stdlib.h>.
 * This compat shim lets upstream C++ sources (vk_fg.cpp, vk_fsr3.cpp) compile unmodified. */
#pragma once
#include <stdlib.h>
