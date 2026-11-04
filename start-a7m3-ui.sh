#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
work="$root/work"
qemu="${QEMU_SYSTEM_ARM:-$work/qemu-src/build-a7m3/qemu-system-arm}"
image="$work/kbuild-ui/arch/arm/boot/Image"
cross="${CROSS_COMPILE:-$work/armv7-eabihf--glibc--stable-2020.08-1/bin/arm-linux-}"
[[ -x "$qemu" && -f "$image" ]] || { echo 'Run build-qemu.sh and build-kernel.sh first' >&2; exit 1; }
[[ -f "$work/initramfs-ui/usr/kmod/dma330_stub.ko" && -f "$work/fakeroot.state" ]] || { echo 'Prepare initramfs and kernel modules first' >&2; exit 1; }
cp "$root/source/initramfs/init-ui.sh" "$work/initramfs-ui/init"
chmod +x "$work/initramfs-ui/init"
"${cross}gcc" -shared -fPIC -O2 -Wall -Wextra -Werror -o "$work/initramfs-ui/usr/lib/libuiobserve.so" "$root/source/ui/ui-observe.c" -ldl -pthread
mkdir -p "$root/evidence/ui-startup"
python3 "$root/scripts/prepare-ui-profile.py" > "$root/evidence/ui-startup/ap-profile.json"
fakeroot -i "$work/fakeroot.state" -- bash -o pipefail -c 'cd "$1" && find . -print0 | cpio --null -o -H newc --quiet --owner=0:0' bash "$work/initramfs-ui" > "$work/ui.cpio.part"
mv "$work/ui.cpio.part" "$work/ui.cpio"
exec "$qemu" -M a7m3 -cpu cortex-a9 -smp 1 -m 1024 \
    -kernel "$image" -initrd "$work/ui.cpio" \
    -append 'console=ttyAM0,115200n8 cfg.uart=1 amba2.console=1 mem=1G@0 memrsv=0x1A5E000@0x02E68000 memrsv=512M@0x20000000:uc rdinit=/init loglevel=8' \
    -display none -serial stdio -monitor none -no-reboot "$@"
