# A7M3 Linux 内核适配

源码来自 Sony **ILCE-7M3 Ver.4.04** 的 `linux-kernel.tar.gz`，版本为 Linux 3.0.27。

- 官方索引：<https://oss.sony.net/Products/Linux/DI/ILCE-7M3_Ver404.html>
- 归档：<https://prodgpl.blob.core.windows.net/download/DI/ILCE-7M3_Ver.4.04/linux-kernel.tar.gz>
- SHA256：`3840107cd5cad0c3ba63b845c4ffa8e37aed58932cba5975e133d4bdb033d478`
- 许可：原归档的 `COPYING`，随此目录保留。

## 构建

从项目根目录先按 [docs/setup.md](../../docs/setup.md) 准备固件、工具链和 `work/camera.cpio`，然后执行：

```bash
./build-kernel.sh
```

脚本校验源码摘要，解出 Sony 归档顶层的 `linux/`，重命名为 `work/linux-kernel/` 后应用补丁。归档自带 `.config` 保全为 `work/sony-original-kernel.config`，避免它阻止 O= 构建。独立构建目录为 `work/kbuild-ui/`，输出镜像为 `work/kbuild-ui/arch/arm/boot/Image`。

默认使用 `sources/sony-ilce7m3-ver404/linux-kernel.tar.gz` 和 Bootlin ARM GCC 9.3.0。`SONY_KERNEL_ARCHIVE` 可指定已校验的其他归档路径，`CROSS_COMPILE` 可指定同一工具链的前缀。

## 改动范围

`0001-a7m3-qemu.patch` 沿用同代 ZV-E10 的 40 文件补丁，针对旧汇编语法、ATAGS 指针、initramfs 链接位置、MMCI 注册、DDR alias、procfs 和 `put_user` 寄存器处理提供本机适配，并添加 GCC 9 兼容头。

`a7m3_defconfig` 使用同代 CXD900X0 ARM32 配置，其 initramfs 路径由构建脚本指定。本机生成的 kernel release 为 `3.0.27_nl-rt106+`，与 A7M3 原厂模块的 vermagic 一致。

## 实际验证

本次已对 A7M3 4.04 自身的公开源码执行补丁 dry-run 和实际应用，40 个文件均干净应用。随后完整构建 `Image modules` 及本地 `dma330_stub.ko`，原厂所需模块在 A7M3 QEMU 中加载成功，原 `bootin.elf`／`im.elf` 能运行原厂 UI。

这验证了所述本机配置的启动与原模块消费，不证明所有 procfs workaround 或 DDR alias 与真实相机等价。内核未用于物理相机，不作为可刷写固件交付。完整系统和 UI 验收见[主报告](../../report/2026-11-04-a7m3-qemu-bringup/README.md)。
