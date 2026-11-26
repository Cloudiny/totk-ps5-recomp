/*
 * ps5/trophies_ps5.c
 *
 * PlayStation 5 Trophy system for Tears of the Kingdom v1.4.3 (PPSA99199).
 * Parses TOTK progress.sav MurmurHash3-32 flag table (< 1 ms per save commit),
 * persists unlocked trophies per PS5 user in <TOTK_PROFILE_DIR>/trophies.json,
 * and fires both native PS5 OS notifications and in-game PS5 trophy banners.
 */

#include "trophies_ps5.h"

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

extern void rt_log(const char *fmt, ...);
extern uint64_t plat_now_ns(void);

/* Native PS5 system notification ABI (verified in third_party/ps5-kit win32_ps5.c) */
struct ps5_notification {
    uint8_t reserved[45];
    char message[3075];
};
extern int sceKernelSendNotificationRequest(int device, struct ps5_notification *request, size_t size, int blocking);

/* MurmurHash3-32 (seed 0) matching TOTK progress.sav GameData keys */
static uint32_t murmur3_32(const char *s) {
    const uint8_t *b = (const uint8_t *)s;
    size_t n = strlen(s);
    uint32_t h1 = 0u;
    const uint32_t c1 = 0xcc9e2d51u;
    const uint32_t c2 = 0x1b873593u;
    size_t nblocks = n / 4u;
    for (size_t i = 0; i < nblocks; ++i) {
        uint32_t k1;
        memcpy(&k1, b + i * 4u, 4u);
        k1 *= c1;
        k1 = (k1 << 15) | (k1 >> 17);
        k1 *= c2;
        h1 ^= k1;
        h1 = (h1 << 13) | (h1 >> 19);
        h1 = h1 * 5u + 0xe6546b64u;
    }
    const uint8_t *tail = b + nblocks * 4u;
    uint32_t k1 = 0u;
    switch (n & 3u) {
    case 3: k1 ^= (uint32_t)tail[2] << 16; /* fallthrough */
    case 2: k1 ^= (uint32_t)tail[1] << 8;  /* fallthrough */
    case 1:
        k1 ^= (uint32_t)tail[0];
        k1 *= c1;
        k1 = (k1 << 15) | (k1 >> 17);
        k1 *= c2;
        h1 ^= k1;
    }
    h1 ^= (uint32_t)n;
    h1 ^= h1 >> 16;
    h1 *= 0x85ebca6bu;
    h1 ^= h1 >> 13;
    h1 *= 0xc2b2ae35u;
    h1 ^= h1 >> 16;
    return h1;
}

typedef enum {
    EVAL_BOOL_FLAG = 0,
    EVAL_BOTH_FLAGS = 1,
    EVAL_SHRINES = 2,
    EVAL_TOWERS = 3,
    EVAL_LIGHTROOTS = 4,
    EVAL_TEARS = 5,
    EVAL_STAMINA_POST_PROLOGUE = 6,
    EVAL_HEARTS_POST_PROLOGUE = 7,
    EVAL_PLATINUM = 8
} TrophyEvalKind;

typedef struct {
    const char *id;
    const char *title;
    const char *desc;
    Ps5TrophyTier tier;
    TrophyEvalKind kind;
    uint32_t h1;
    uint32_t h2;
    int target;
} TrophyDef;

/* All flag hashes below were empirically verified against TOTK v1.4.3 progress.sav */
static const TrophyDef kTrophies[] = {
    /* --- Historia Principal & Habilidades --- */
    {"prologo_cueva",     "Bajo el Castillo de Hyrule",   "Explora el subterraneo junto a la princesa Zelda.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xdacf54fdu, 0u, 1},
    {"despertar_ganon",   "El Despertar del Rey Demonio", "Presencia el despertar de Ganondorf.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0x6c4f88f5u, 0u, 1},
    {"tableta_prunia",    "Tableta de Prunia",            "Despierta en la Gran Isla Celeste y recibe la Tableta.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xb0e23924u, 0u, 1},
    {"ultramano",         "Arquitecto Zonnan",            "Obten el poder de la Ultramano.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0x8816dc32u, 0u, 1},
    {"combinacion",       "Forjador Creativo",            "Obten el poder de la Combinacion.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xa2e3b2aau, 0u, 1},
    {"retroceso",         "Senor del Tiempo",             "Obten el poder del Retroceso.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0x21eededeu, 0u, 1},
    {"cuatro_santuarios", "El Salto hacia Hyrule",        "Completa los 4 santuarios de la Gran Isla Celeste.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xebb2f29du, 0u, 1},
    {"generador",         "Ingeniero del Subsuelo",       "Obten el poder del Generador (Autobuild).",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0x51330f2bu, 0u, 1},
    {"sabio_viento",      "Juramento del Viento",         "Completa el Templo del Viento y consigue el pacto de Tureli.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0x463ac522u, 0u, 1},
    {"sabio_fuego",       "Juramento del Fuego",          "Completa el Templo del Fuego y consigue el pacto de Yunobo.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0x30351796u, 0u, 1},
    {"sabio_agua",        "Juramento del Agua",           "Completa el Templo del Agua y consigue el pacto de Sidon.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0xf6e42b3bu, 0u, 1},
    {"sabio_trueno",      "Juramento del Trueno",         "Completa el Templo del Trueno y consigue el pacto de Riju.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0x5b1cd8c0u, 0u, 1},
    {"sabio_espiritu",    "El Quinto Sabio",              "Despierta al Sabio del Espiritu, Mineru.",
     PS5_TROPHY_GOLD,     EVAL_BOOL_FLAG, 0xda6d9225u, 0u, 1},
    {"fantasma_castillo", "Sombra en el Castillo",        "Derrota al espectro en el Castillo de Hyrule.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0x5231d012u, 0u, 1},
    {"espada_maestra",    "Espada Destructora del Mal",   "Recupera la legendaria Espada Maestra.",
     PS5_TROPHY_GOLD,     EVAL_BOOL_FLAG, 0x3f48a65fu, 0u, 1},
    {"rey_demonio",       "Lagrimas del Reino",           "Derrota al Rey Demonio Ganondorf y completa la historia.",
     PS5_TROPHY_GOLD,     EVAL_BOOL_FLAG, 0xb4962feeu, 0u, 1},

    /* --- Exploracion: Santuarios, Atalayas, Subsuelo y Lagrimas --- */
    {"primer_santuario",  "Primera Luz Luminosa",         "Completa tu primer Santuario.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xf9360377u, 0u, 1},
    {"santuarios_25",     "Peregrino de la Luz",          "Descubre 25 Santuarios en Hyrule.",
     PS5_TROPHY_BRONZE,   EVAL_SHRINES,   0u, 0u, 25},
    {"santuarios_75",     "Buscador de Santuarios",       "Descubre 75 Santuarios en Hyrule.",
     PS5_TROPHY_SILVER,   EVAL_SHRINES,   0u, 0u, 75},
    {"santuarios_152",    "Maestro de los Santuarios",    "Descubre los 152 Santuarios de Hyrule.",
     PS5_TROPHY_GOLD,     EVAL_SHRINES,   0u, 0u, 152},
    {"primera_atalaya",   "Ojos en el Cielo",             "Activa tu primera Atalaya.",
     PS5_TROPHY_BRONZE,   EVAL_TOWERS,    0u, 0u, 1},
    {"atalayas_8",        "Cartografo del Reino",         "Activa 8 Atalayas en Hyrule.",
     PS5_TROPHY_SILVER,   EVAL_TOWERS,    0u, 0u, 8},
    {"atalayas_15",       "Mapa Completo de Hyrule",      "Activa las 15 Atalayas del reino.",
     PS5_TROPHY_GOLD,     EVAL_TOWERS,    0u, 0u, 15},
    {"raices_10",         "Luz en la Oscuridad",          "Ilumina 10 Raices del Subsuelo.",
     PS5_TROPHY_BRONZE,   EVAL_LIGHTROOTS, 0u, 0u, 10},
    {"raices_60",         "Explorador del Subsuelo",      "Ilumina 60 Raices del Subsuelo.",
     PS5_TROPHY_SILVER,   EVAL_LIGHTROOTS, 0u, 0u, 60},
    {"raices_120",        "Disipador de Tinieblas",       "Ilumina todas las Raices del Subsuelo.",
     PS5_TROPHY_GOLD,     EVAL_LIGHTROOTS, 0x69b72b52u, 0u, 120},
    {"lagrimas_1",        "Ecos del Pasado",              "Encuentra tu primera Lagrima de Dragon.",
     PS5_TROPHY_BRONZE,   EVAL_TEARS,     0u, 0u, 1},
    {"lagrimas_12",       "Memoria del Dragon",           "Descubre las 12 Lagrimas de Dragon.",
     PS5_TROPHY_GOLD,     EVAL_TEARS,     0u, 0u, 12},

    /* --- Maestria, Herramientas y Secundarias --- */
    {"primer_kolog",      "Yahaha!",                      "Encuentra tu primera semilla de Kolog.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0x5ba15424u, 0u, 1},
    {"kolog_amigo",       "Buen Samaritano",              "Ayuda a un Kolog cansado a reunirse con su amigo.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xf1b6f664u, 0u, 1},
    {"camara_sensor",     "Investigador de Prunia",       "Obten la Camara y el Sensor Sheikah+.",
     PS5_TROPHY_BRONZE,   EVAL_BOTH_FLAGS, 0xb8a1847fu, 0xcd16f59fu, 1},
    {"gran_hada_1",       "Bendicion de las Hadas",       "Despierta a tu primera Gran Hada.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0x85572a8bu, 0u, 1},
    {"grandes_hadas_4",   "Coro de las Hadas",            "Despierta a las 4 Grandes Hadas.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0x968126ecu, 0u, 1},
    {"arbol_deku",        "Salvador del Bosque Kolog",    "Libera al Gran Arbol Deku del aura maligna.",
     PS5_TROPHY_SILVER,   EVAL_BOOL_FLAG, 0xdf39f0c5u, 0u, 1},
    {"casa_propia",       "Hogar en Aldea Arkadia",       "Construye tu propia casa en Aldea Arkadia.",
     PS5_TROPHY_BRONZE,   EVAL_BOOL_FLAG, 0xa5fe7a34u, 0u, 1},
    {"vigor_maximo",      "Aliento Infinito",             "Alcanza las 3 ruedas completas de Vigor tras despertar.",
     PS5_TROPHY_SILVER,   EVAL_STAMINA_POST_PROLOGUE, 0xb0e23924u, 0xf9212c74u, 3000},
    {"corazones_20",      "Corazon de Heroe",             "Alcanza 20 corazones tras despertar en la Isla Celeste.",
     PS5_TROPHY_SILVER,   EVAL_HEARTS_POST_PROLOGUE,  0xb0e23924u, 0xfbe01da1u, 20},
    {"platino_totk",      "Leyenda de las Lagrimas",      "Desbloquea todos los trofeos de Tears of the Kingdom.",
     PS5_TROPHY_PLATINUM, EVAL_PLATINUM,  0u, 0u, 37},
};

#define NUM_TROPHIES ((int)(sizeof(kTrophies) / sizeof(kTrophies[0])))

typedef struct {
    int unlocked;
    uint64_t unlocked_at;
    int cur;
} TrophyState;

static pthread_mutex_t g_tr_mu = PTHREAD_MUTEX_INITIALIZER;
static TrophyState g_state[NUM_TROPHIES];
static int g_loaded_from_disk = 0;
static char g_json_path[512];
static char g_user_label[96] = "PS5 User";

/* Toast banner queue */
#define BANNER_Q_CAP 64
static int g_banner_q[BANNER_Q_CAP];
static int g_banner_head = 0;
static int g_banner_tail = 0;
static int g_banner_active = -1;
static uint64_t g_banner_start_ns = 0;

/* Precomputed hash tables for dynamic multi-entry counters */
static uint32_t g_shrine_hashes[160];
static uint32_t g_tower_hashes[15];
static uint32_t g_lightroot_hashes[160];
static uint32_t g_tear_hashes[12];
static int g_hashes_init = 0;

static void init_counter_hashes(void) {
    if (g_hashes_init) return;
    char buf[64];
    for (int i = 0; i < 160; ++i) {
        snprintf(buf, sizeof(buf), "IsVisitLocation.Dungeon%03d", i);
        g_shrine_hashes[i] = murmur3_32(buf);
        snprintf(buf, sizeof(buf), "IsVisitLocation.CheckPoint%03d", i);
        g_lightroot_hashes[i] = murmur3_32(buf);
    }
    for (int i = 0; i < 15; ++i) {
        snprintf(buf, sizeof(buf), "IsOpenCannon.Tower%02d", i + 1);
        g_tower_hashes[i] = murmur3_32(buf);
    }
    for (int i = 0; i < 12; ++i) {
        snprintf(buf, sizeof(buf), "Complete_DragonTears%02d", i + 1);
        g_tear_hashes[i] = murmur3_32(buf);
    }
    g_hashes_init = 1;
}

static const char *tier_name_es(Ps5TrophyTier t) {
    switch (t) {
    case PS5_TROPHY_PLATINUM: return "Platino";
    case PS5_TROPHY_GOLD:     return "Oro";
    case PS5_TROPHY_SILVER:   return "Plata";
    default:                  return "Bronce";
    }
}

static void send_ps5_system_notification(const TrophyDef *def) {
    struct ps5_notification note;
    memset(&note, 0, sizeof(note));
    snprintf(note.message, sizeof(note.message),
             "Trofeo %s desbloqueado!\n%s - %s",
             tier_name_es(def->tier), def->title, def->desc);
    (void)sceKernelSendNotificationRequest(0, &note, sizeof(note), 0);
}

static void enqueue_banner_locked(int idx) {
    int next = (g_banner_tail + 1) % BANNER_Q_CAP;
    if (next == g_banner_head) return;
    g_banner_q[g_banner_tail] = idx;
    g_banner_tail = next;
}

static void resolve_paths_locked(void) {
    if (g_json_path[0]) return;
    const char *prof = getenv("TOTK_PROFILE_DIR");
    if (!prof || !*prof) prof = "/data/totk-ps5/saves";
    snprintf(g_json_path, sizeof(g_json_path), "%s/trophies.json", prof);

    const char *slash = strrchr(prof, '/');
    if (slash && slash[1]) {
        snprintf(g_user_label, sizeof(g_user_label), "%s", slash + 1);
    }
}

static void load_json_locked(void) {
    resolve_paths_locked();
    if (g_loaded_from_disk) return;
    g_loaded_from_disk = 1;

    FILE *fp = fopen(g_json_path, "rb");
    if (!fp) return;
    fseek(fp, 0, SEEK_END);
    long sz = ftell(fp);
    if (sz <= 0 || sz > 256 * 1024) {
        fclose(fp);
        return;
    }
    rewind(fp);
    char *buf = (char *)malloc((size_t)sz + 1u);
    if (!buf) {
        fclose(fp);
        return;
    }
    size_t nr = fread(buf, 1, (size_t)sz, fp);
    fclose(fp);
    buf[nr] = '\0';

    /* Simple, dependency-free JSON loader for our own trophies.json */
    for (int i = 0; i < NUM_TROPHIES; ++i) {
        char pat[96];
        snprintf(pat, sizeof(pat), "\"%s\"", kTrophies[i].id);
        char *p = strstr(buf, pat);
        if (!p) continue;
        char *u = strstr(p, "\"unlocked\":");
        char *next_obj = strchr(p + 1, '}');
        if (u && (!next_obj || u < next_obj)) {
            if (strstr(u, "true") && (!next_obj || strstr(u, "true") < next_obj)) {
                g_state[i].unlocked = 1;
            }
        }
        char *ts = strstr(p, "\"unlocked_at\":");
        if (ts && (!next_obj || ts < next_obj)) {
            g_state[i].unlocked_at = strtoull(ts + 14, NULL, 10);
        }
    }
    free(buf);
}

static void save_json_locked(void) {
    resolve_paths_locked();
    char tmp[540];
    snprintf(tmp, sizeof(tmp), "%s.tmp", g_json_path);
    FILE *fp = fopen(tmp, "wb");
    if (!fp) return;

    int unlocked = 0;
    for (int i = 0; i < NUM_TROPHIES; ++i) {
        if (g_state[i].unlocked) unlocked++;
    }

    fprintf(fp, "{\n  \"title_id\": \"PPSA99199\",\n  \"user\": \"%s\",\n  \"unlocked\": %d,\n  \"total\": %d,\n  \"trophies\": [\n",
            g_user_label, unlocked, NUM_TROPHIES);
    for (int i = 0; i < NUM_TROPHIES; ++i) {
        fprintf(fp,
                "    {\"id\": \"%s\", \"tier\": \"%s\", \"title\": \"%s\", \"unlocked\": %s, \"unlocked_at\": %llu, \"cur\": %d, \"target\": %d}%s\n",
                kTrophies[i].id,
                tier_name_es(kTrophies[i].tier),
                kTrophies[i].title,
                g_state[i].unlocked ? "true" : "false",
                (unsigned long long)g_state[i].unlocked_at,
                g_state[i].cur,
                kTrophies[i].target,
                (i + 1 < NUM_TROPHIES) ? "," : "");
    }
    fprintf(fp, "  ]\n}\n");
    fclose(fp);
    rename(tmp, g_json_path);
}

typedef struct {
    uint32_t hash;
    uint32_t val;
} SavEntry;

static int cmp_sav_entry(const void *a, const void *b) {
    uint32_t ha = ((const SavEntry *)a)->hash;
    uint32_t hb = ((const SavEntry *)b)->hash;
    return (ha > hb) - (ha < hb);
}

static int find_sav_val(const SavEntry *arr, size_t n, uint32_t hash, uint32_t *out) {
    size_t lo = 0, hi = n;
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2u;
        if (arr[mid].hash < hash) lo = mid + 1u;
        else if (arr[mid].hash > hash) hi = mid;
        else {
            if (out) *out = arr[mid].val;
            return 1;
        }
    }
    return 0;
}

static int find_newest_progress_sav(const char *save_root, char *out_path, size_t cap) {
    time_t best_mtime = 0;
    int found = 0;
    for (int slot = 0; slot <= 5; ++slot) {
        char cand[512];
        snprintf(cand, sizeof(cand), "%s/slot_%02d/progress.sav", save_root, slot);
        struct stat st;
        if (stat(cand, &st) == 0 && S_ISREG(st.st_mode) && st.st_size >= 0x30) {
            if (!found || st.st_mtime >= best_mtime) {
                best_mtime = st.st_mtime;
                snprintf(out_path, cap, "%s", cand);
                found = 1;
            }
        }
    }
    return found;
}

void ps5_trophies_scan_save(const char *save_root) {
    if (!save_root || !*save_root) return;
    init_counter_hashes();

    char sav_path[512];
    if (!find_newest_progress_sav(save_root, sav_path, sizeof(sav_path))) return;

    FILE *fp = fopen(sav_path, "rb");
    if (!fp) return;

    uint32_t hdr[10];
    if (fread(hdr, sizeof(uint32_t), 10, fp) != 10 || hdr[0] != 0x01020304u) {
        fclose(fp);
        return;
    }
    uint32_t end_off = hdr[2];
    if (end_off <= 0x28u || end_off > 4u * 1024u * 1024u) {
        fclose(fp);
        return;
    }
    size_t table_bytes = (size_t)(end_off - 0x28u);
    size_t n_entries = table_bytes / sizeof(SavEntry);
    SavEntry *entries = (SavEntry *)malloc(n_entries * sizeof(SavEntry));
    if (!entries) {
        fclose(fp);
        return;
    }
    size_t got = fread(entries, sizeof(SavEntry), n_entries, fp);
    fclose(fp);
    if (got == 0) {
        free(entries);
        return;
    }
    qsort(entries, got, sizeof(SavEntry), cmp_sav_entry);

    /* Count dynamic collections once per scan */
    int shrines = 0, towers = 0, lightroots = 0, tears = 0;
    uint32_t v = 0;
    for (int i = 0; i < 160; ++i) {
        if (find_sav_val(entries, got, g_shrine_hashes[i], &v) && v != 0) shrines++;
        if (find_sav_val(entries, got, g_lightroot_hashes[i], &v) && v != 0) lightroots++;
    }
    for (int i = 0; i < 15; ++i) {
        if (find_sav_val(entries, got, g_tower_hashes[i], &v) && v != 0) towers++;
    }
    for (int i = 0; i < 12; ++i) {
        if (find_sav_val(entries, got, g_tear_hashes[i], &v) && v != 0) tears++;
    }

    int newly_unlocked[NUM_TROPHIES];
    int newly_n = 0;

    pthread_mutex_lock(&g_tr_mu);
    load_json_locked();
    int changed = 0;
    int non_plat_unlocked = 0;
    uint64_t now_unix = (uint64_t)time(NULL);

    for (int i = 0; i < NUM_TROPHIES; ++i) {
        const TrophyDef *d = &kTrophies[i];
        int met = 0;
        int cur = g_state[i].unlocked ? d->target : 0;

        switch (d->kind) {
        case EVAL_BOOL_FLAG: {
            uint32_t val = 0;
            if (find_sav_val(entries, got, d->h1, &val) && val != 0) {
                met = 1;
                cur = 1;
            }
            break;
        }
        case EVAL_BOTH_FLAGS: {
            uint32_t v1 = 0, v2 = 0;
            int m1 = find_sav_val(entries, got, d->h1, &v1) && v1 != 0;
            int m2 = find_sav_val(entries, got, d->h2, &v2) && v2 != 0;
            cur = (m1 ? 1 : 0) + (m2 ? 1 : 0);
            met = (m1 && m2);
            break;
        }
        case EVAL_SHRINES:
            cur = shrines;
            met = (shrines >= d->target);
            break;
        case EVAL_TOWERS:
            cur = towers;
            met = (towers >= d->target);
            break;
        case EVAL_LIGHTROOTS: {
            uint32_t reward = 0;
            int has_rew = (d->h1 != 0) && find_sav_val(entries, got, d->h1, &reward) && reward != 0;
            cur = has_rew ? d->target : lightroots;
            met = has_rew || (lightroots >= d->target);
            break;
        }
        case EVAL_TEARS:
            cur = tears;
            met = (tears >= d->target);
            break;
        case EVAL_STAMINA_POST_PROLOGUE: {
            uint32_t has_pad = 0, raw_st = 0;
            if (find_sav_val(entries, got, d->h1, &has_pad) && has_pad != 0 &&
                find_sav_val(entries, got, d->h2, &raw_st)) {
                float st = 0.0f;
                memcpy(&st, &raw_st, sizeof(float));
                cur = (int)st;
                met = (st >= (float)d->target - 1.0f);
            }
            break;
        }
        case EVAL_HEARTS_POST_PROLOGUE: {
            uint32_t has_pad = 0, max_life = 0;
            if (find_sav_val(entries, got, d->h1, &has_pad) && has_pad != 0 &&
                find_sav_val(entries, got, d->h2, &max_life)) {
                int hearts = (int)(max_life / 4u);
                cur = hearts;
                met = (hearts >= d->target);
            }
            break;
        }
        case EVAL_PLATINUM:
            cur = non_plat_unlocked;
            met = (non_plat_unlocked >= d->target);
            break;
        }

        if (cur > g_state[i].cur) {
            g_state[i].cur = cur;
            changed = 1;
        }
        if (met && !g_state[i].unlocked) {
            g_state[i].unlocked = 1;
            g_state[i].unlocked_at = now_unix;
            g_state[i].cur = d->target;
            changed = 1;
            enqueue_banner_locked(i);
            newly_unlocked[newly_n++] = i;
        }
        if (d->kind != EVAL_PLATINUM && g_state[i].unlocked) {
            non_plat_unlocked++;
        }
    }

    if (changed) save_json_locked();
    pthread_mutex_unlock(&g_tr_mu);
    free(entries);

    /* Fire native PS5 system notifications outside lock */
    for (int k = 0; k < newly_n; ++k) {
        const TrophyDef *d = &kTrophies[newly_unlocked[k]];
        rt_log("ps5-trophy: UNLOCKED [%s] %s (%s)", tier_name_es(d->tier), d->title, d->id);
        send_ps5_system_notification(d);
    }
}

int ps5_trophies_count(void) { return NUM_TROPHIES; }

int ps5_trophies_get(int index, Ps5TrophyView *out) {
    if (!out || index < 0 || index >= NUM_TROPHIES) return 0;
    pthread_mutex_lock(&g_tr_mu);
    load_json_locked();
    const TrophyDef *d = &kTrophies[index];
    out->id = d->id;
    out->title = d->title;
    out->desc = d->desc;
    out->tier = d->tier;
    out->unlocked = g_state[index].unlocked;
    out->unlocked_at = g_state[index].unlocked_at;
    out->cur = g_state[index].cur;
    out->target = d->target;
    pthread_mutex_unlock(&g_tr_mu);
    return 1;
}

void ps5_trophies_summary(int *unlocked_total, int *bronze, int *silver, int *gold, int *platinum) {
    int u = 0, b = 0, s = 0, g = 0, p = 0;
    pthread_mutex_lock(&g_tr_mu);
    load_json_locked();
    for (int i = 0; i < NUM_TROPHIES; ++i) {
        if (!g_state[i].unlocked) continue;
        u++;
        switch (kTrophies[i].tier) {
        case PS5_TROPHY_BRONZE:   b++; break;
        case PS5_TROPHY_SILVER:   s++; break;
        case PS5_TROPHY_GOLD:     g++; break;
        case PS5_TROPHY_PLATINUM: p++; break;
        }
    }
    pthread_mutex_unlock(&g_tr_mu);
    if (unlocked_total) *unlocked_total = u;
    if (bronze) *bronze = b;
    if (silver) *silver = s;
    if (gold) *gold = g;
    if (platinum) *platinum = p;
}

const char *ps5_trophies_user_label(void) {
    pthread_mutex_lock(&g_tr_mu);
    resolve_paths_locked();
    pthread_mutex_unlock(&g_tr_mu);
    return g_user_label;
}

int ps5_trophies_toast_active(void) {
    pthread_mutex_lock(&g_tr_mu);
    int active = (g_banner_active >= 0) || (g_banner_head != g_banner_tail);
    pthread_mutex_unlock(&g_tr_mu);
    return active;
}

int ps5_trophies_current_banner(Ps5TrophyView *out, float *alpha_out) {
    const uint64_t dur_ns = 5000000000ull; /* 5.0 seconds per trophy banner */
    uint64_t now = plat_now_ns();
    int ok = 0;
    float alpha = 0.0f;

    pthread_mutex_lock(&g_tr_mu);
    if (g_banner_active >= 0 && now - g_banner_start_ns >= dur_ns) {
        g_banner_active = -1;
    }
    if (g_banner_active < 0 && g_banner_head != g_banner_tail) {
        g_banner_active = g_banner_q[g_banner_head];
        g_banner_head = (g_banner_head + 1) % BANNER_Q_CAP;
        g_banner_start_ns = now;
    }
    if (g_banner_active >= 0 && g_banner_active < NUM_TROPHIES) {
        uint64_t el = now - g_banner_start_ns;
        float sec = (float)((double)el / 1e9);
        if (sec < 0.35f) alpha = sec / 0.35f;
        else if (sec > 4.4f) alpha = (5.0f - sec) / 0.6f;
        else alpha = 1.0f;
        if (alpha < 0.0f) alpha = 0.0f;
        if (alpha > 1.0f) alpha = 1.0f;

        if (out) {
            const TrophyDef *d = &kTrophies[g_banner_active];
            out->id = d->id;
            out->title = d->title;
            out->desc = d->desc;
            out->tier = d->tier;
            out->unlocked = 1;
            out->unlocked_at = g_state[g_banner_active].unlocked_at;
            out->cur = d->target;
            out->target = d->target;
        }
        ok = 1;
    }
    pthread_mutex_unlock(&g_tr_mu);
    if (alpha_out) *alpha_out = alpha;
    return ok;
}
