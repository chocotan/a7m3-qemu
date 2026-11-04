#include <assert.h>
#include <stdio.h>
#include "../source/ui/ui-input-command.h"
int main(void)
{
    assert(ui_command_action("menu",4)==1);
    assert(ui_command_action("back",4)==2);
    assert(ui_command_action("snapshot",8)==3);
    assert(ui_command_action("enter",5)==4);
    assert(ui_command_action("disp",4)==5);
    assert(!ui_command_action(NULL,4));
    assert(!ui_command_action("",0));
    assert(!ui_command_action("menu\0junk",9));
    assert(!ui_command_action(" menu",5));
    assert(!ui_command_action("menu ",5));
    assert(!ui_command_action("menu\r",5));
    assert(!ui_command_action("shutdown",8));
    assert(!ui_command_action("menus",5));
    puts("PASS: exact UART command whitelist, lengths and embedded NUL rejection");
}
