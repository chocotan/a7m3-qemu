# 输入与源码来源

本工程使用 Sony ILCE-7M3 4.04 固件及该版本公开的 Linux 源码。固件包、解包后的系统和本地运行输出保存在忽略目录中。

## Sony 源码

官方索引：<https://oss.sony.net/Products/Linux/DI/ILCE-7M3_Ver404.html>

2026-11-04 已下载该页列出的全部 **25 个源码包**，共 **263,513,506 字节**：3 个 tar.gz 和 22 个 src.rpm。各包 URL、大小及摘要见[公开下载清单](validation/source-downloads.json)。源码包含 Linux 3.0.27、compat-wireless、qrencode，以及 BusyBox、coreutils、dosfstools、e2fsprogs、GCC 运行库、glibc、hostname、iperf、iptables、libnl、libusb-compat、procps、pump、rpm、soundtouch 和 util-linux。页面列出的不同版本均保留。

本次工作区下载保存在 `../../sources/sony-ilce7m3-ver404/`。公开 checkout 的脚本默认写入仓库内被忽略的 `sources/sony-ilce7m3-ver404/`。其中 `manifest.json` 保存每包原始 URL、最终 URL、大小和 SHA256，`SHA256SUMS` 保存独立校验清单；`pages/` 保存官方页面快照，`verification.json` 保存下载和归档检查结果。tar.gz 已检查归档结构及压缩流，RPM 已检查文件头，尚未逐包解开 RPM 载荷。

```bash
python3 scripts/download-sources.py
(cd sources/sony-ilce7m3-ver404 && sha256sum -c SHA256SUMS)
```

需要复用本次工作区的下载时，运行 `SONY_KERNEL_ARCHIVE="$PWD/../../sources/sony-ilce7m3-ver404/linux-kernel.tar.gz" ./build-kernel.sh`。下载目录可通过 `--dest` 指定。

内核归档 SHA256：

```text
3840107cd5cad0c3ba63b845c4ffa8e37aed58932cba5975e133d4bdb033d478  linux-kernel.tar.gz
```

## 原厂固件

输入为用户已有的 `Update_ILCE7M3V404.exe`，只按数据文件解析。解出 DAT 后的内部版本元数据为 `4.04`，型号值为 `0x71030014`，架构为 ARM32。

| 输入 | SHA256 |
| --- | --- |
| Update_ILCE7M3V404.exe | `8c356688a70946a855191e99fd4d9096a5c3d4263f3f11065605eaea45639d57` |
| FirmwareData_ILCE7M3V404.dat | `7f5c9597ee8ceb5a80255976a6e8cd8035639b4362dd7bd328ca2f6401846bda` |
| 原厂 libObj.so | `1117453a969c9dedeb9bf6b006514fd9c2644a79085590a797189df109d64d23` |
| 原厂 viewUnified2.so | `f561a1e5fa0d10d55727dd4a10ced97c9613b698a40b489ff9317634485e5129` |

EXE 包装器中的 `ProductName` 留有其他型号名称，工程以 DAT 校验和及内部型号/版本确认输入。设置使用更新包自带的 `0110_backup/SYSASTRA-DSLR/TI/CX62200_ALLLANG.bin`，不读取真实相机的私人设置。

## 模拟器与工具链

| 组件 | 固定版本／来源 |
| --- | --- |
| 参考工程 | 用户已有 `/home/choco/Downloads/zve10-qemu`，移植时保持只读 |
| QEMU | [11.1.2 官方源码](https://download.qemu.org/qemu-11.1.2.tar.xz)，SHA256 `731b5681e4bb18be313231579b8efd0296c5b015fa36dc533874b639ba838016` |
| DTC | 构建所需固定归档、版本和许可证说明见 [source/qemu/README.md](source/qemu/README.md) |
| ARM 编译器 | [Bootlin armv7-eabihf glibc stable-2020.08-1](https://toolchains.bootlin.com/downloads/releases/toolchains/armv7-eabihf/tarballs/armv7-eabihf--glibc--stable-2020.08-1.tar.bz2)，GCC 9.3.0 |
| fwtool | [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py)，本机使用 commit `72fbdd15ddcc2d2a24ccb52cf8e84b8de98c738a` |

内核补丁来自同代 ZV-E10 适配，经 A7M3 自身源码重新应用和构建。UI 地址按 A7M3 自身 ELF 重定位；静态校验工具为 [scripts/relocate-ui.py](scripts/relocate-ui.py)。QEMU 中的设备模型用于本地功能模拟，实机 ASIC 兼容性另行标为未验证。
