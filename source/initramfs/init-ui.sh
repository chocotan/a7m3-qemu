#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
export LD_LIBRARY_PATH=/usr/lib:/lib
unset LD_PRELOAD
exec >/dev/kmsg 2>&1
mount -t proc proc /proc || exit 1
mount -t sysfs sysfs /sys || exit 1
mount -t devtmpfs devtmpfs /dev || exit 1
echo A7M3_UI_BOOT
load() {
    insmod "$@"
    result=$?
    echo "MODULE_END $1 status=$result"
    [ "$result" = 0 ] || exit 1
}
load /kmod/devno.ko
load /kmod/dmac.ko
load /usr/kmod/osal_utm.ko
load /usr/kmod/osal_uipc.ko
load /usr/kmod/dma330_stub.ko
load /usr/kmod/backup.ko Backup_load=1 Backup_save=0
load /usr/kmod/utimer.ko
load /usr/kmod/osal_ulogio.ko ulogio_initfile=/setting/ulogio.bin
load /usr/kmod/kikilog.ko
load /usr/kmod/stream.ko
load /usr/kmod/stream2.ko
load /usr/kmod/dmm.ko DmmConfig=/setting/DmmConfig.bin
load /usr/kmod/grm_ma.ko
load /usr/kmod/grm_gles.ko
for spec in 'uipc 251 207' 'backup 251 208' 'dmpgles2 248 29' 'stream 249 7' 'stream2 249 8' 'ldec 251 205'; do
    set -- $spec
    [ -e /dev/"$1" ] || mknod /dev/"$1" c "$2" "$3"
done
LD_PRELOAD=/usr/lib/libuiobserve.so /usr/bin/bootin.elf 'target=qemu ' dmode=3 amode=normal &
echo "A7M3_BOOTIN_PID=$!"
sleep 100000
