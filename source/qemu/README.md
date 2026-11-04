# A7M3 独立 QEMU 构建

2026-11-04 已从本地 QEMU 11.1.2 原始归档构建出独立的 `qemu-system-arm`，实际注册、创建并正常退出 `a7m3` board。它沿用参考工程的同代 CXD90045-family 功能模型；本次结果只证明构建与设备创建，不证明 A7M3 原固件已经启动，也不证明物理 ASIC 兼容、图像处理或拍摄完成。

本项只修改本项目的 `source/qemu/`、`build-qemu.sh` 和 `work/qemu-src/`，未修改 UI、init、kernel、scripts 或参考工程。依据[根目录约定](../../../../AGENTS.md)与本次明确授权，只运行本机 QEMU；验证没有 guest 网卡、磁盘或物理设备，没有提交代码。

## 复现构建

在 `final/a7m3-qemu` 项目根目录执行：

```bash
./build-qemu.sh
./work/qemu-src/build-a7m3/qemu-system-arm -M help
```

脚本要求本机已经安装 Bash、GNU tar/xz、patch、coreutils、C 编译工具链、pkg-config、Python 3、Meson、Ninja，以及 GLib、Pixman、SDL2 的开发文件。此次环境为 GCC 16.2.1、Meson 1.12.1、Ninja 1.13.2、Python 3.14.7、GLib 2.90.1、Pixman 0.46.4、SDL2 2.32.74。

默认原始归档为项目根目录下的 `work/qemu-11.1.2.tar.xz`；也可用环境变量 `QEMU_TARBALL` 指定同一摘要的本地文件。脚本不下载依赖，并执行以下固定步骤：

1. 校验 QEMU 与随附 DTC 归档的 SHA-256。
2. 首次运行时提取到 `work/qemu-src/`；已有源码必须为 11.1.2，非空的残缺目录会保留并报错。
3. 解开随附 DTC，应用注册补丁，复制三个 board/timer 文件。已应用的同一补丁可重复识别；冲突直接报错。
4. 在 `work/qemu-src/build-a7m3/` 配置并执行 `ninja -j8 qemu-system-arm`。
5. 通过 QMP 实际创建 board、检查设备和映射、检查没有 guest 磁盘或网卡，然后正常 `quit`，写入日志、JSON 与二进制摘要。

配置参数为：

```bash
../configure --target-list=arm-softmmu --disable-download \
    --without-default-features --enable-tcg --enable-fdt=internal \
    --enable-pixman --enable-sdl --disable-werror \
    --disable-tools --disable-guest-agent --disable-docs
ninja -j8 qemu-system-arm
```

SDL 编译支持不代表 board 已实现相机显示硬件。SLIRP、vhost 和其他自动可选功能未启用。实际运行时仍须显式使用 `-nic none`，且仅向 guest 提供项目内的虚拟文件。验证会话使用 `-S -nodefaults -display none -serial none -monitor none -nic none`，没有传入 `-drive` 或内核。

## 离线依赖与变更

| 输入 | 固定版本或 SHA-256 | 用途 |
| --- | --- | --- |
| `qemu-11.1.2.tar.xz` | `731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016` | 原始 QEMU；保留原文件不修改 |
| [dtc-b6910bec.tar.xz](dtc-b6910bec.tar.xz) | `c1fb23f4f39fc88da4a1f89b06ea13e8683de886ee77dbb99369f8763dfe809e` | 完整本地 DTC 源码，含原许可证 |
| DTC Git 提交 | `b6910bec11614980a21e46fbccc35934b671bd81` | 与 QEMU 归档的 `subprojects/dtc.wrap` 完全一致 |

原始归档已包含其余必需子项目与 Python wheels，唯一缺少的 DTC 从 `~/Downloads/zve10-qemu/work/qemu-src/subprojects/dtc` 只读打包；未改动参考目录。本项目后续重建使用随附 DTC，不再依赖参考工程或其二进制。

重命名审查修正了遗留的 `Zve10Gpe` C 类型名；机器、宏、环境变量、日志标签、内存区域和文件名均为 A7M3。注册补丁补上 `select PL181`，并把 `sony_hwtimer.c` 的编译条件由 `CONFIG_ARM_VIRT` 改为 `CONFIG_A7M3`，使 board 的 timer 实现不再依赖另一台机器被启用。没有凭重命名改动继承的地址、IRQ 或硬件语义。

## 实际结果与证据

验证时间为 2026-11-04 05:40:54 UTC。构建执行 2015 个 Ninja 步骤，以链接 `qemu-system-arm` 结束，无编译警告或错误；构建驱动退出码为 0。输出为本机 x86-64 ELF 动态链接可执行文件，约 90 MiB；它模拟的目标为 ARM，运行时仅依赖本机系统库。

| 证据 | 观察与结论 | 复现路径 |
| --- | --- | --- |
| E-001：[注册补丁](0001-register-a7m3.patch)与[board](hw/arm/a7m3.c) | F-001：`CONFIG_A7M3` 注册 `a7m3.c` 并编译 Sony timer，显式选择 PL181 | P-001：`./build-qemu.sh` → 源码提取与补丁 → arm-softmmu 配置 |
| E-002：[完整构建驱动日志](../../work/qemu-src/build-driver.log)、[Ninja 日志](../../work/qemu-src/build-a7m3/build.log) | F-002：独立二进制完成实际链接；不是参考工程可执行文件的链接或复制 | P-001：`ninja -j8 qemu-system-arm` → [最终二进制](../../work/qemu-src/build-a7m3/qemu-system-arm) |
| E-003：[verification.json](../../work/qemu-src/build-a7m3/verification.json)、[原始 QMP](../../work/qemu-src/build-a7m3/verification-qmp.log) | F-003：实际创建 `a7m3-machine`、一个 Cortex-A9、九个 Sony timer、PL181、PL011、GPE/Sugilite 区域；无 guest 网卡或磁盘，QMP quit 后退出码为 0 | P-001：构建脚本自检 → `qom-get` / `info qtree` / `info mtree` → `quit` |
| E-004：[默认 CPU 验证](../../work/qemu-src/build-a7m3/default-cpu-smoke.log) | F-004：不显式指定 `-cpu` 时，`-M a7m3` 也能创建机器并正常退出；QEMU 自动使用唯一允许的 Cortex-A9 | P-002：省略 `-cpu` 的同类无盘、无网 QMP 会话 |

本次二进制 SHA-256：

```text
379757c560e9cb6a2d7da25084057eb665f8879dfc7afa63725b02c80823dc65
```

`verification.json` SHA-256：

```text
3d7e98e040aab6b182079d718771c032c2257014da92c569a355dcd250094a2f
```

脚本使用固定源、依赖和配置参数；上述二进制摘要标识本次主机产物，不承诺不同工具链、路径和主机间逐字节相同。已检查补丁反向 dry-run 可完整识别，且交付的三个 C/header 文件与实际构建源码逐字节一致。`bash -n` 通过；脚本中的 QMP assert 是随构建执行的自检。

## 同代复用局限

| 模型部分 | 当前行为 | 尚未证明的部分 |
| --- | --- | --- |
| CPU / RAM / 启动 | Cortex-A9，默认 1 GiB，继承 board ID 3497、loader 地址与 ATAGS 约定 | A7M3 实机内存与启动布局；原固件完整启动、SMP |
| 中断与计时 | A9 MPCore、九个共享 Sony timer，继承 MMIO/IRQ 与 4 MHz 输入时钟 | A7M3 每路 IRQ、时钟与计数语义均吻合 |
| UART / 存储 | PL011 与 PL181 功能设备 | 原 SoC 的 UART、SD DMA、控制寄存器和时序精确兼容；原 AP 实际写卡 |
| Sugilite / GPE | 电源状态固定读值 `0x15`；仅识别参考工程已捕获的一种启动同步包，回送其 fence token | GPU 命令解释、真实绘制/合成；该同步包属于 A7M3 的证据 |
| 其余 SoC | `unimplemented` 区域读零、写忽略；已建模区域优先 | 时钟、复位、GPIO、传感器、镜头、AF、ISP、JPEG/视频编码 |

`firmware_boot_verified` 与 `physical_asic_compatibility_verified` 均保持 false。上述启动桩不能作为 ready、图像消费或成片成功证据；本任务未修改它们的参考行为。原固件启动、拍摄主界面、输入、CMOS/镜头/AF、编码与虚拟 SD 成片验收由后续集成单独验证。
