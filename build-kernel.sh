#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
work="$root/work"
archive="${SONY_KERNEL_ARCHIVE:-$root/sources/sony-ilce7m3-ver404/linux-kernel.tar.gz}"
cross="${CROSS_COMPILE:-$work/armv7-eabihf--glibc--stable-2020.08-1/bin/arm-linux-}"
if [[ ! -d "$work/linux-kernel" ]]; then
    echo '3840107cd5cad0c3ba63b845c4ffa8e37aed58932cba5975e133d4bdb033d478'"  $archive" | sha256sum -c -
    tar -xzf "$archive" -C "$work"
    mv "$work/linux" "$work/linux-kernel"
    patch -d "$work/linux-kernel" -p1 < "$root/source/kernel/0001-a7m3-qemu.patch"
fi
if [[ -f "$work/linux-kernel/.config" ]]; then
    mv "$work/linux-kernel/.config" "$work/sony-original-kernel.config"
fi
mkdir -p "$work/kbuild-ui"
if [[ ! -f "$work/kbuild-ui/.config" ]]; then
    cp "$root/source/kernel/a7m3_defconfig" "$work/kbuild-ui/.config"
fi
[[ -f "$work/camera.cpio" ]] || { echo 'Prepare initramfs first' >&2; exit 1; }
"$work/linux-kernel/scripts/config" --file "$work/kbuild-ui/.config" --set-str INITRAMFS_SOURCE "$work/camera.cpio"
make -C "$work/linux-kernel" O="$work/kbuild-ui" ARCH=arm CROSS_COMPILE="$cross" oldnoconfig
make -C "$work/linux-kernel" O="$work/kbuild-ui" ARCH=arm CROSS_COMPILE="$cross" -j"${JOBS:-16}" Image modules
mkdir -p "$work/modules"
cp -a "$root/source/modules/." "$work/modules/"
make -C "$work/linux-kernel" O="$work/kbuild-ui" ARCH=arm CROSS_COMPILE="$cross" M="$work/modules/dma330-stub" modules
cp "$work/modules/dma330-stub/dma330_stub.ko" "$work/initramfs-ui/usr/kmod/"
