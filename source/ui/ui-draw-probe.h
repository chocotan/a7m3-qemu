#ifndef UI_DRAW_PROBE_H
#define UI_DRAW_PROBE_H

/* Keep the native draw boundary; diagnostic object walks are intentionally absent. */
typedef uintptr_t (*gemini_probe_fn5)(uintptr_t, uintptr_t, uintptr_t, uintptr_t, uintptr_t);
typedef uintptr_t (*gemini_probe_fn6)(uintptr_t, uintptr_t, uintptr_t, uintptr_t, uintptr_t, uintptr_t);
static gemini_probe_fn5 gemini_original_solid;
static gemini_probe_fn6 gemini_original_rect, gemini_original_quad, gemini_original_line;
static unsigned gemini_kind_count[4];
static inline void inspect_gemini_counts(void)
{
    record("GEMINI.total.solid",gemini_kind_count[0]);
    record("GEMINI.total.textrect",gemini_kind_count[1]);
    record("GEMINI.total.quad",gemini_kind_count[2]);
    record("GEMINI.total.line",gemini_kind_count[3]);
}
static uint32_t gemini_probe_read(uintptr_t p, unsigned offset)
{
    uint32_t value;
    memcpy(&value,(const void *)(p+offset),sizeof value);
    return value;
}
static void gemini_probe_texture(const char *name, uintptr_t texture, const char *bitmap_name)
{
    record(name,texture);
    if (texture >= 4096 && texture <= UINT32_MAX-0x4c)
        record(bitmap_name,gemini_probe_read(texture,0x48));
}
static uintptr_t gemini_probe_solid(uintptr_t r, uintptr_t s, uintptr_t m, uintptr_t c, uintptr_t dst)
{
    ++gemini_kind_count[0];
    return gemini_original_solid(r,s,m,c,dst);
}
static uintptr_t gemini_probe_rect(uintptr_t r, uintptr_t s, uintptr_t m, uintptr_t c, uintptr_t src, uintptr_t dst)
{
    ++gemini_kind_count[1];
    return gemini_original_rect(r,s,m,c,src,dst);
}
static uintptr_t gemini_probe_quad(uintptr_t r, uintptr_t s, uintptr_t m, uintptr_t c, uintptr_t src, uintptr_t points)
{
    ++gemini_kind_count[2];
    return gemini_original_quad(r,s,m,c,src,points);
}
static uintptr_t gemini_probe_line(uintptr_t r, uintptr_t s, uintptr_t m, uintptr_t c, uintptr_t first, uintptr_t second)
{
    ++gemini_kind_count[3];
    return gemini_original_line(r,s,m,c,first,second);
}
#define GEMINI_PROBE_HOOKS \
    {0x80ad58, {0x2d,0xe9,0xf0,0x47,0x2d,0xed,0x04,0x8b}, (void *)gemini_probe_solid, NULL}, \
    {0x80aa40, {0x2d,0xe9,0xf0,0x4f,0x2d,0xed,0x06,0x8b}, (void *)gemini_probe_rect, NULL}, \
    {0x80a758, {0x2d,0xe9,0xf0,0x4f,0x2d,0xed,0x06,0x8b}, (void *)gemini_probe_quad, NULL}, \
    {0x80aedc, {0x2d,0xe9,0xf0,0x4f,0x83,0xb0,0x02,0xaf}, (void *)gemini_probe_line, NULL}
#endif
