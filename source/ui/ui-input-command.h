#ifndef A7M3_UI_INPUT_COMMAND_H
#define A7M3_UI_INPUT_COMMAND_H
#include <stddef.h>
#include <string.h>
static int ui_command_action(const char *command, size_t length)
{
    if (!command) return 0;
    if (length==4 && !memcmp(command,"menu",4)) return 1;
    if (length==4 && !memcmp(command,"back",4)) return 2;
    if (length==8 && !memcmp(command,"snapshot",8)) return 3;
    if (length==5 && !memcmp(command,"enter",5)) return 4;
    if (length==4 && !memcmp(command,"disp",4)) return 5;
    return 0;
}
#endif
