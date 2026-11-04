#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "ui-raster.h"
#include "ui-gemini-raster.h"
#include "ui-present.h"
#include "ui-lz77.h"
#include "ui-input-command.h"

/* A7M3 ELF32 cold hooks: install before the original UI lifecycle starts. */
typedef uintptr_t (*entry_fn)(uintptr_t,uintptr_t,uintptr_t,uintptr_t);
static entry_fn original_draw, original_rm_execute, original_engine_wait;
static long present_completed_tid;
static unsigned draw_count, raster_count, raster_failed;
static int installed, memory_fd=-1;
static uintptr_t object_base, views_base;
static void software_range_clear(uint32_t *request);
static void inspect_gemini_counts(void);
static void try_original_menu(void);
static inline void headless_request_capture(void);
static int shooting_page_opened, root_page_requested, ui_action_request, main_view_seen;

static void record(const char *name, uintptr_t value)
{
    char line[160];
    int length=snprintf(line,sizeof line,"UI_OBSERVE pid=%d tid=%ld %s=%#lx\n",
        getpid(),syscall(224),name,(unsigned long)value);
    if (length>0 && length<(int)sizeof line) write(2,line,length);
}
static uintptr_t observe_draw(uintptr_t a,uintptr_t b,uintptr_t c,uintptr_t d)
{
    unsigned frame=++draw_count;
    if (frame<=8) record("drawFramebuffer.enter",a);
    uintptr_t result=original_draw(a,b,c,d);
    if (frame<=8) {
        record("drawFramebuffer.return",a);
        inspect_gemini_counts();
    }
    try_original_menu();
    return result;
}
#include "ui-image-decode.h"

/* Called on the original UI thread. The host command never opens a menu at boot. */
static void try_original_menu(void)
{
    if (!object_base || !views_base) return;
    uintptr_t manager=ui_u32((void *)(object_base+0x13289f4)); /* pViewManager */
    if (manager<4096 || manager>UINT32_MAX-36) return;
    unsigned count=ui_u32((void *)manager);
    uintptr_t slots=ui_u32((void *)(manager+32));
    if (!count || count>256 || slots<4096 || slots>UINT32_MAX-count*16) return;
    uintptr_t root=0, root_page=0, shooting_page=0;
    int menu_open=0;
    for (unsigned i=0;i<count;++i) {
        uintptr_t view=ui_u32((void *)(slots+i*16+4));
        if (view<4096 || view>UINT32_MAX-0x128) continue;
        uintptr_t vptr=ui_u32((void *)view);
        if (vptr==views_base+0x87d738) root=view;
        if (vptr==views_base+0x87ba90) root_page=view;
        if (vptr==views_base+0x878328) shooting_page=view;
        unsigned id=ui_u32((void *)(slots+i*16+8));
        if (id==0x11 || id==0xba || id==0x5a) menu_open=1;
    }
    if (shooting_page && !main_view_seen) {
        main_view_seen=1;
        record("native.main.instance",shooting_page);
    }
    /* RTTI proves the menu owner moved from RootSelector+0x154 to +0x124. */
    uintptr_t owner=root ? root+0x124 : 0;
    if (!owner || ui_u32((void *)owner)!=views_base+0x87d930) return;
    if (!shooting_page_opened) {
        entry_fn open=dlsym(RTLD_NEXT,"_ZN8ViewBase8openViewEPKcib");
        if (!open) return;
        if (!root_page_requested) {
            unsigned value=0;
            int (*read_backup)(int,void *)=dlsym(RTLD_NEXT,"_ZN13BackupManager9Bkup_ReadEiPv");
            if (read_backup) record("native.models.backup_read",read_backup(0x003e000b,&value));
            record("native.models.integrated",(uintptr_t)value);
            root_page_requested=1;
            open(root,(uintptr_t)"view/ROOT",0,0);
            record("native.root.request.return",1);
            return;
        }
        if (!root_page) return;
        __sync_lock_test_and_set(&shooting_page_opened,1);
        record("native.main.root",root);
        record("native.root.instance",root_page);
        record("native.selector.state",ui_u32((void *)(root+4)));
        if (!shooting_page) open(root,(uintptr_t)"view/STLREC",0,0);
        record("native.main.request.return",1);
        return;
    }
    int action=__sync_lock_test_and_set(&ui_action_request,0);
    if (action==1) {
        /* The AP-only startup has no CP transition to install RootSelector's trigger table. */
        record("native.menu.already_open",menu_open);
        if (!menu_open) ((void (*)(uintptr_t,int))(views_base+0x2bcfe1))(owner,0);
        record("native.menu.request.return",1);
    } else if (action==2) {
        void (*close_view)(uintptr_t,const char *)=dlsym(RTLD_NEXT,"_ZN8ViewBase9closeViewEPKc");
        if (!close_view) _exit(71);
        close_view(root,"@V0BA");
        close_view(root,"@V011");
        record("native.menu.close.return",1);
    }
}

static void *input_worker(void *unused)
{
    (void)unused;
    int fd=open("/dev/ttyAM0",O_RDONLY|O_NOCTTY|O_CLOEXEC);
    if (fd<0) { record("input.open.error",errno); return NULL; }
    unsigned long enabled=1;
    if (ioctl(fd,_IOW('u',2,unsigned long),&enabled)) {
        record("input.enable.error",errno); close(fd); return NULL;
    }
    struct termios terminal;
    if (tcgetattr(fd,&terminal)) { record("input.termios.error",errno); close(fd); return NULL; }
    cfmakeraw(&terminal);
    if (tcsetattr(fd,TCSANOW,&terminal)) { record("input.raw.error",errno); close(fd); return NULL; }
    record("input.ready",1);
    char command[32]; unsigned length=0;
    for (;;) {
        char byte;
        ssize_t n=read(fd,&byte,1);
        if (n<0 && errno==EINTR) continue;
        if (n!=1) { record("input.read.error",errno); close(fd); return NULL; }
        if (byte!='\n') {
            if (length<sizeof command-1) command[length++]=byte;
            continue;
        }
        int action=ui_command_action(command,length);
        length=0;
        if (!action || !__sync_fetch_and_add(&shooting_page_opened,0)) continue;
        headless_request_capture();
        if (action==3) { record("input.snapshot",1); continue; }
        void (*callback)(int,uint32_t *)=dlsym(RTLD_NEXT,"_ZN12InputService16callback_convertEiP16_InfraInputEvent");
        if (!callback) { record("input.callback.error",1); continue; }
        uint32_t base=action==4 ? 0x15010060 : action==5 ? 0x150101a0 : 0x15010110;
        uint32_t event[6]={base,0,0,0,0,0};
        callback(0,event);
        record(action>=4 ? "input.key.press" : "input.menu.press",event[0]+1);
        usleep(50000);
        event[2]=1;
        callback(0,event);
        record(action>=4 ? "input.key.release" : "input.menu.release",event[0]+2);
        if (action<=2) __sync_lock_test_and_set(&ui_action_request,action);
    }
}

static uintptr_t observe_rm_execute(uintptr_t a,uintptr_t b,uintptr_t c,uintptr_t d)
{
    uint32_t *request=(void *)a;
    uint32_t flags=request[0];
    int cpu_clear=request[1]==3 && !(flags&2);
    if (cpu_clear) {
        software_range_clear(request);
        request[0]=flags|2; /* Native skip-hardware branch retires the real callbacks. */
    }
    uintptr_t result=original_rm_execute(a,b,c,d);
    if (cpu_clear) request[0]=flags;
    return result;
}

struct surface_mapping {
    void *base;
    unsigned char *pixels;
    size_t length;
};
static int map_surface(uint32_t physical, size_t span, struct surface_mapping *m)
{
    if (physical < 0x20000000u || physical >= 0x40000000u || span > 0x40000000u - physical)
        return -5;
    if (memory_fd < 0) memory_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (memory_fd < 0) return -5;
    unsigned delta = physical & 4095;
    m->length = (span + delta + 4095) & ~(size_t)4095;
    m->base = mmap(NULL, m->length, PROT_READ|PROT_WRITE, MAP_SHARED, memory_fd, physical & ~4095u);
    if (m->base == MAP_FAILED) return -5;
    m->pixels = (unsigned char *)m->base + delta;
    return 0;
}
static void software_range_clear(uint32_t *request)
{
    size_t span = ui_range_clear_span(request);
    struct surface_mapping dst;
    if (!span || map_surface(request[15],span,&dst)) {
        record("GPE.clear.UNSUPPORTED", request[15]);
        record("GPE.clear.end", request[16]);
        record("GPE.clear.pattern", request[17]);
        record("GPE.clear.control", request[18]);
        _exit(71);
    }
    int result = ui_range_clear(dst.pixels,span,request);
    __sync_synchronize();
    if (munmap(dst.base,dst.length) || result) {
        record("GPE.clear.error", result ? (uintptr_t)result : (uintptr_t)errno);
        _exit(71);
    }
    record("GPE.clear.start", request[15]);
    record("GPE.clear.cleared", span);
}

static uintptr_t software_present(uintptr_t params, uintptr_t b, uintptr_t c, uintptr_t d)
{
    (void)b; (void)c; (void)d;
    const unsigned char *p = (void *)params;
    size_t span = ui_present_span(p);
    if (present_completed_tid || !span) {
        record("GPE.present.UNSUPPORTED", params);
        if (p) for (unsigned i = 0; i < 14; ++i) record("GPE.present.param", ui_u32(p + i * 4));
        _exit(71);
    }
    struct surface_mapping src, dst;
    if (map_surface(ui_u32(p),span,&src)) {
        record("GPE.present.source.error", errno);
        _exit(71);
    }
    if (map_surface(ui_u32(p + 4),span,&dst)) {
        record("GPE.present.destination.error", errno);
        munmap(src.base,src.length);
        _exit(71);
    }
    int result = ui_present_copy(dst.pixels,span,src.pixels,span,p);
    __sync_synchronize();
    int unmap_error = munmap(dst.base,dst.length);
    unmap_error |= munmap(src.base,src.length);
    if (result || unmap_error) {
        record("GPE.present.copy.error", result ? (uintptr_t)result : (uintptr_t)errno);
        _exit(71);
    }
    present_completed_tid = syscall(224);
    record("GPE.present.source", ui_u32(p));
    record("GPE.present.destination", ui_u32(p + 4));
    record("GPE.present.copied", span);
    return 0;
}
static uintptr_t software_engine_wait(uintptr_t engine, uintptr_t b, uintptr_t c, uintptr_t d)
{
    uint32_t status = ui_present_take_completion(&present_completed_tid,syscall(224),(unsigned)engine);
    if (status) {
        record("GPE.present.completed", status);
        return status;
    }
    return original_engine_wait(engine,b,c,d);
}

static void dump_params(const char *label, const unsigned char *p, unsigned length)
{
    record(label, ++raster_count);
    for (unsigned i = 0; i < length; i += 4) record("DMP.param", ui_u32(p + i));
}
static uintptr_t software_init(uintptr_t a, uintptr_t b, uintptr_t c, uintptr_t d)
{
    (void)a; (void)b; (void)c; (void)d;
    record("DMP.cpu.initialize", 1);
    return 0;
}
static uintptr_t software_exit(uintptr_t a, uintptr_t b, uintptr_t c, uintptr_t d)
{
    (void)a; (void)b; (void)c; (void)d;
    record("DMP.cpu.exit", raster_failed);
    return 0;
}
static uintptr_t software_fill(uintptr_t request, uintptr_t mode, uintptr_t params, uintptr_t unused)
{
    (void)unused;
    const unsigned char *p = (void *)params;
    size_t span;
    struct surface_mapping m;
    int status = -5;
    if (!p || mode > 2) return (uintptr_t)-5;
    if (raster_count < 8) dump_params("DMP.fill", p, 48);
    if (!ui_surface(p, &span) && !map_surface(ui_u32(p), span, &m)) {
        status = ui_fill(m.pixels, span, p);
        munmap(m.base, m.length);
    }
    if (status) { ++raster_failed; record("DMP.fill.UNSUPPORTED", raster_failed); return (uintptr_t)status; }
    if (ui_u32(p + 40)) ((void (*)(uint32_t, uint32_t))(uintptr_t)ui_u32(p + 40))(request, ui_u32(p + 44));
    return 0;
}
static uintptr_t software_blit(uintptr_t request, uintptr_t mode, uintptr_t params, uintptr_t unused)
{
    (void)unused;
    const unsigned char *p = (void *)params;
    size_t ss, ds;
    struct surface_mapping src, dst;
    int status = -5;
    if (!p || mode > 2) return (uintptr_t)-5;
    if (raster_count < 8) dump_params("DMP.blit", p, 156);
    unsigned char desc[24] = {0};
    memcpy(desc, p + 24, 8); memcpy(desc + 16, p + 48, 8);
    if (!ui_surface(p, &ss) && !ui_surface(desc, &ds)) {
        uint32_t s = ui_u32(p), d = ui_u32(p + 24);
        if ((uint64_t)s + ss <= d || (uint64_t)d + ds <= s) {
            if (!map_surface(s, ss, &src)) {
                if (!map_surface(d, ds, &dst)) {
                    status = ui_blit(dst.pixels, ds, src.pixels, ss, p);
                    munmap(dst.base, dst.length);
                }
                munmap(src.base, src.length);
            }
        }
    }
    if (status) { ++raster_failed; record("DMP.blit.UNSUPPORTED", raster_failed); return (uintptr_t)status; }
    if (ui_u32(p + 148)) ((void (*)(uint32_t, uint32_t))(uintptr_t)ui_u32(p + 148))(request, ui_u32(p + 152));
    return 0;
}

#include "ui-headless.h"

struct hook {
    uint32_t offset;
    unsigned char prologue[8];
    void *replacement, *original;
};
#include "ui-draw-probe.h"
#include "ui-gemini-backend.h"
#include "ui-slow-clear.h"
#include "ui-font-probe.h"

static struct hook hooks[]={
    {0x5e8490,{0xb0,0xb5,0x04,0x46,0x82,0xb0,0x00,0xaf},observe_draw,&original_draw},
    {0x799790,{0x03,0x48,0x80,0xb4,0x78,0x44,0x00,0xaf},software_init,NULL},
    {0x7997b0,{0x03,0x48,0x80,0xb4,0x78,0x44,0x00,0xaf},software_exit,NULL},
    {0x7997d0,{0x02,0x29,0x0b,0x46,0xf0,0xb5,0x85,0xb0},software_fill,NULL},
    {0x799860,{0x02,0x29,0x0b,0x46,0xf0,0xb5,0x85,0xb0},software_blit,NULL},
    {0x73a100,{0x2d,0xe9,0xf0,0x41,0x84,0xb0,0x05,0x46},software_present,NULL},
    {0x73a330,{0xf0,0xb5,0x83,0xb0,0x44,0x1e,0x00,0xaf},software_engine_wait,&original_engine_wait},
    {0x6bf350,{0xb0,0xb5,0x0c,0x46,0x86,0xb0,0x1c,0x49},software_headless_update,NULL},
    {0x60ec64,{0x2d,0xe9,0xf0,0x4f,0x8d,0xb0,0x00,0xaf},software_lz_decode,NULL},
    GEMINI_PROBE_HOOKS,
    FONT_PROBE_HOOKS,
};

static void thumb_jump(unsigned char *where, uintptr_t to)
{
    const unsigned char instruction[] = {0xdf,0xf8,0x00,0xf0}; /* ldr.w pc,[pc,#0] */
    memcpy(where, instruction, 4);
    uint32_t target = to;
    memcpy(where + 4, &target, 4);
}
static int install_rm_hook(uintptr_t base, uint32_t offset, const unsigned char expected[12], entry_fn replacement, entry_fn *original)
{
    unsigned char *address = (void *)(base + offset);
    if (memcmp(address, expected, 12)) { record("RM.prologue.unsupported", offset); return -1; }
    uint16_t load = ui_u16(address + 6);
    if ((load & 0xf800) != 0x4800) return -1;
    uint32_t literal = *(uint32_t *)(((uintptr_t)(address + 10) & ~(uintptr_t)3) + (load & 255) * 4);
    unsigned char *code = mmap(NULL, 4096, PROT_READ|PROT_WRITE|PROT_EXEC, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    if (code == MAP_FAILED) return -1;
    if (mprotect((void *)((uintptr_t)address & ~(uintptr_t)4095),4096,PROT_READ|PROT_WRITE|PROT_EXEC)) {
        munmap(code,4096); return -1;
    }
    memcpy(code,address,12);
    uint16_t relocated = (load & 0xff00) | 3; /* pool at +20, PC at +8 */
    memcpy(code + 6,&relocated,2);
    thumb_jump(code + 12,((uintptr_t)address + 12) | 1);
    memcpy(code + 20,&literal,4);
    *original = (entry_fn)((uintptr_t)code | 1);
    __builtin___clear_cache((char *)code,(char *)code + 24);
    thumb_jump(address,(uintptr_t)replacement);
    __builtin___clear_cache((char *)address,(char *)address + 8);
    return 0;
}

static void install(void *handle)
{
    if (installed) return;
    void *getter=dlsym(handle,"_ZN2ux6wgtsys12WidgetSystem15sys_getInstanceEv");
    Dl_info info;
    if (!getter || !dladdr(getter,&info) || !info.dli_fbase) return;
    uintptr_t base=(uintptr_t)info.dli_fbase;
    if (((uintptr_t)getter&~(uintptr_t)1)-base!=0x5e5dc0) {
        record("unsupported.libObj",(uintptr_t)getter-base); return;
    }
    static const unsigned char executor[12]={0x2d,0xe9,0xf0,0x4f,0x87,0xb0,0xc6,0x4d,0x04,0xaf,0x04,0x46};
    if (memcmp((void *)(base+0x73a470),executor,12)) {
        record("unsupported.RM.prologue",0x73a470); return;
    }
    for (unsigned i=0;i<sizeof hooks/sizeof hooks[0];++i)
        if (memcmp((void *)(base+hooks[i].offset),hooks[i].prologue,8)) {
            record("unsupported.prologue",hooks[i].offset); return;
        }
    unsigned char *tramp=mmap(NULL,4096,PROT_READ|PROT_WRITE|PROT_EXEC,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (tramp==MAP_FAILED) { record("mmap.error",errno); return; }
    for (unsigned i=0;i<sizeof hooks/sizeof hooks[0];++i) {
        uintptr_t address=base+hooks[i].offset;
        if (mprotect((void *)(address&~(uintptr_t)4095),4096,PROT_READ|PROT_WRITE|PROT_EXEC)) {
            record("mprotect.error",errno); munmap(tramp,4096); return;
        }
        if (hooks[i].original) {
            memcpy(tramp+i*16,(void *)address,8);
            thumb_jump(tramp+i*16+8,(address+8)|1);
            uintptr_t target=(uintptr_t)(tramp+i*16)|1;
            memcpy(hooks[i].original,&target,sizeof target);
        }
    }
    if (install_rm_hook(base,0x73a470,executor,observe_rm_execute,&original_rm_execute)) {
        record("RM.hook.failed",errno); munmap(tramp,4096); return;
    }
    object_base=base;
    gemini_original_solid=software_gemini_solid;
    gemini_original_rect=software_gemini_rect;
    gemini_original_quad=software_gemini_quad;
    gemini_original_line=software_gemini_line;
    __builtin___clear_cache((char *)tramp,(char *)tramp+sizeof hooks/sizeof hooks[0]*16);
    for (unsigned i=0;i<sizeof hooks/sizeof hooks[0];++i) {
        unsigned char *address=(void *)(base+hooks[i].offset);
        thumb_jump(address,(uintptr_t)hooks[i].replacement);
        __builtin___clear_cache((char *)address,(char *)address+8);
    }
    installed=1;
    record("RM.hooks.installed",1);
    record("hooks.installed.base",base);
    pthread_t thread;
    int status=pthread_create(&thread,NULL,input_worker,NULL);
    if (status) { record("input.thread.error",status); _exit(71); }
    pthread_detach(thread);
}

void *dlopen(const char *path,int flags)
{
    static void *(*native_dlopen)(const char *,int);
    if (!native_dlopen) native_dlopen=dlvsym(RTLD_NEXT,"dlopen","GLIBC_2.4");
    if (!native_dlopen) { errno=ENOSYS; return NULL; }
    void *handle=native_dlopen(path,flags);
    if (!handle && path) {
        char line[256];
        int n=snprintf(line,sizeof line,"UI_LOAD_FAILED path=%s\n",path);
        if (n>0 && n<(int)sizeof line) write(2,line,n);
    }
    if (handle && path && strstr(path,"libObj.so")) install(handle);
    if (handle && path && strstr(path,"viewUnified2.so")) {
        void *factory=dlsym(handle,"ViewRootSelectorToInstance");
        Dl_info info;
        if (factory && dladdr(factory,&info) && info.dli_fbase &&
            (((uintptr_t)factory&~(uintptr_t)1)-(uintptr_t)info.dli_fbase)==0x2839a4) {
            views_base=(uintptr_t)info.dli_fbase;
            record("native.menu.views.base",views_base);
        }
    }
    return handle;
}
__attribute__((constructor)) static void loaded(void)
{
    record("library.loaded",1);
}
