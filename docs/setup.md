# 从固件与源码构建

以下命令在 `a7m3-qemu/` 根目录执行，面向 Linux x86_64。所有镜像都在本机实验目录生成，不连接真实相机。

## 安装依赖

Debian／Ubuntu 需要 GCC、Make、Ninja、Meson、GLib、Pixman、SDL2、cpio、7-Zip、e2fsprogs、fakeroot、patch、Git、curl，以及 Python 3、Pillow、Tk、pyelftools 和 Capstone。

```bash
sudo apt install build-essential ninja-build meson pkg-config \
  libglib2.0-dev libpixman-1-dev libsdl2-dev python3 python3-venv \
  python3-pil python3-tk python3-pyelftools python3-capstone \
  cpio p7zip-full e2fsprogs fakeroot patch git curl bc bison flex
mkdir -p work
```

## 下载 Sony 全部源码

```bash
python3 scripts/download-sources.py
```

默认保存在仓库内被忽略的 `sources/sony-ilce7m3-ver404/`。源码清单和固定输入摘要见 [SOURCES.md](../SOURCES.md)。本次多项目工作区已有下载位于 `../../sources/sony-ilce7m3-ver404/`，可通过 `SONY_KERNEL_ARCHIVE` 直接复用。

## 准备固件和工具链

将支持的 `Update_ILCE7M3V404.exe` 放在项目根目录。准备脚本会核对完整更新包和内嵌 DAT 的 SHA256。

```bash
git clone https://github.com/ma1co/fwtool.py work/fwtool
git -C work/fwtool checkout 72fbdd15ddcc2d2a24ccb52cf8e84b8de98c738a
python3 -m venv work/fwtool-venv
work/fwtool-venv/bin/pip install pycryptodome pyyaml
curl -fL --retry 3 \
  https://toolchains.bootlin.com/downloads/releases/toolchains/armv7-eabihf/tarballs/armv7-eabihf--glibc--stable-2020.08-1.tar.bz2 \
  -o work/armv7-toolchain.tar.bz2
tar -xjf work/armv7-toolchain.tar.bz2 -C work
fakeroot -s work/fakeroot-extract.state python3 scripts/prepare-firmware.py \
  --fwtool-python work/fwtool-venv/bin/python
fakeroot -s work/fakeroot.state python3 scripts/prepare-initramfs.py
```

提取脚本先读取 Sony 包装器中的 CAB，交给 fwtool 解析 DAT，然后从原分区恢复系统文件。`work/rootfs`、`work/usr` 等是原始提取结果；运行副本在 `work/initramfs-ui/`。两个准备脚本均拒绝覆盖已有提取目录。重做时先保留原目录，勿清空正在使用的实验。

`fakeroot.state` 保存控制台设备节点信息，后续打包会读取它。不要只复制 initramfs 目录后继续使用旧的 fakeroot 状态。

## 构建内核与 QEMU

```bash
./build-kernel.sh
curl -fL --retry 3 https://download.qemu.org/qemu-11.1.2.tar.xz -o work/qemu-11.1.2.tar.xz
QEMU_TARBALL="$PWD/work/qemu-11.1.2.tar.xz" ./build-qemu.sh
```

`build-kernel.sh` 校验 Sony 内核归档，应用随附的 40 文件适配补丁，保全源码包自带的 `.config`，在独立输出目录构建 `3.0.27_nl-rt106+` 内核及 DMA 符号兼容模块。它使用已经准备好的 `work/camera.cpio`。

`build-qemu.sh` 校验 QEMU 与固定 DTC 归档，离线应用 `a7m3` 板级适配。完成后会用 QMP 验证机器、定时器、串口、内存映射，以及没有虚拟网络或磁盘接入，再正常退出。

## 打开窗口或自动截图

```bash
./start.sh
```

窗口显示原厂提交的 640×480 画面。`MENU` 按钮和键盘 `M` 请求菜单；`确认` 和 `Enter` 处理原提示；`返回` 和 `Esc` 请求关闭菜单；`DISP` 或 `D` 发送原显示事件，刷新请求重新导出原生帧。关闭窗口后，程序发送 QMP `quit` 并等待其启动的 QEMU 结束。

自动保存主页面和菜单截图并退出：

```bash
./start.sh --smoke
```

每次运行的串口日志、RGBA4444 原生像素、PNG、页映射和摘要位于 `output/<时间>/`。截图前暂停 QEMU，按 guest 提供的私有快照页读取物理内存，并独立校验 FNV 与 SHA256。发生错误时保留原日志。

`start-a7m3-ui.sh` 只启动串口服务，不负责窗口和自动关闭。一般使用 `start.sh`。

## 回归

```bash
python3 tests/run-tests.py
python3 scripts/download-sources.py --self-test
xvfb-run -a python3 tests/check-gui.py
```

原帧独立核验使用 `python3 tests/check-runtime-evidence.py`，后面传入本次 `--smoke` 生成的实际 `output/` 目录。

测试覆盖软件绘图、透明度、资源解码、完整清屏、显示完成通知、不可变帧与重取帧、串口命令白名单、提取错误处理和 cpio 设备节点。缺少本地固件资源 fixture 时，两个解码测试会明确输出 `SKIP`；合成用例仍执行。原厂界面的实际消费通过 `--smoke` 和截图核对，不能由主机单元测试替代。

源码地址迁移证据见 [UI 移植说明](../source/ui/PORTING.md)。固件运行边界及尚未完成的显示状态以工程 README 和最新报告为准。
