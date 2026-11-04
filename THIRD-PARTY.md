# 源码和许可证

自行编写的启动脚本、宿主工具和文档采用根目录 [MIT 许可证](LICENSE)。第三方源码、内核补丁及其派生文件遵循各自许可证。

| 内容 | 来源 | 许可证 |
| --- | --- | --- |
| 同代模拟器参考 | [chocotan/zve10-qemu](https://github.com/chocotan/zve10-qemu)，并参考 [a7c2-qemu](https://github.com/chocotan/a7c2-qemu) 的软件绘图方式 | 上游各文件的许可证 |
| QEMU 板级、定时器及接入修改 | [QEMU 11.1.2](https://download.qemu.org/qemu-11.1.2.tar.xz) 与上述参考实现 | GPL-2.0-or-later；保留文件标识，全文见 `source/licenses/QEMU-GPL-2.0.txt` |
| 固定 DTC 构建源码 | `source/qemu/dtc-b6910bec.tar.xz`，来源和摘要见 `source/qemu/README.md` | 归档内各文件的 GPL／BSD 许可 |
| Linux 配置和适配补丁 | [Sony ILCE-7M3 4.04 OSS](https://oss.sony.net/Products/Linux/DI/ILCE-7M3_Ver404.html)，Linux 3.0.27；适配沿用同代参考补丁 | Linux 各文件许可证，全文见 `source/kernel/COPYING` |
| `source/ui/ui-lz77.h` | 改编自 Sony Linux `lib/lz77/lz77_inflate.c` 和 `include/linux/lz77.h` | Sony 原代码 Dual BSD/GPL；保留 Copyright 2006,2007 Sony Corporation 与 BSD 声明 |
| ARM 工具链，单独下载 | Bootlin armv7-eabihf glibc stable-2020.08-1 | 工具链归档内各组件许可证，不随仓库分发 |
| fwtool，单独下载 | [ma1co/fwtool.py](https://github.com/ma1co/fwtool.py) | 上游 MIT，不随仓库分发 |
| Python 依赖 | Pillow、pyelftools、Capstone，及 fwtool 使用的 PyYAML、PyCryptodome | 各上游许可证，不随仓库分发 |

Sony 固件更新包、原厂相机程序、字库、图片资源、设置模板、解包镜像、虚拟磁盘和完整运行日志均不包含在 Git 仓库中。文档中的界面截图来自本机运行，用于说明兼容性和验收结果，不将原厂图标、字体或菜单作为本项目自行设计的资源授权。

输入版本、下载链接和摘要见 [SOURCES.md](SOURCES.md)。内核和功能适配只用于本机模拟器。
