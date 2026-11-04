/* Captured Sugilite startup synchronization packet, not a general GPU interpreter. */
#ifndef A7M3_GPE_INIT_H
#define A7M3_GPE_INIT_H
#include <stdbool.h>
#include <stdint.h>
static inline bool a7m3_gpe_init_packet(const uint32_t p[8])
{
    return p[0] == 0x0116f000 && p[1] >= 0x02000000 && p[1] < 0x02800000 &&
           p[2] == 0x0117f000 && p[3] == 1 && p[4] == 0x0044f000 && p[5] == 0 &&
           p[6] == 0x0010f000 && p[7] == 0x12345678;
}
#endif
