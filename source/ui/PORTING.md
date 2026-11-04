# A7M3 原厂 UI 软件绘图适配

本工程保留 A7M3 原厂页面、字体、图片和控件，由 ARM32 进程中的软件后端消费原绘图请求。宿主窗口只显示已完成的原生帧。它没有模拟完整 CMOS、镜头或 CP。

## 地址验证

[scripts/relocate-ui.py](../../scripts/relocate-ui.py) 记录从同代 ZV-E10 到 A7M3 的 33 个代码、12 个数据和 3 个视图地址映射。[relocation-report.json](relocation-report.json) 验证原始 ELF 摘要、14 个八字节 hook 前导、Thumb 指令边界和 RM trampoline 的 literal 重定位。两个复制到 trampoline 的短前导均没有 PC 相关读取或控制流转移。

需要自己的两份固件 ELF 才能独立重新核对：

```bash
python3 scripts/relocate-ui.py --check \
  --reference /path/to/zve10/usr/lib --target work/usr/lib \
  --report work/ui-relocation-check.json
```

正常构建和运行不需要 ZV-E10 固件。地址表已按 A7M3 4.04 固定，运行时同时检查目标函数的前导字节。

无导出符号的数据项通过原 PC 相对引用和 GOT 分别定位，没有使用统一 BSS 差值：

| 全局项 | ZV-E10 | A7M3 | 独立证据 |
| --- | --- | --- | --- |
| graphics singleton pointer | `0x145cbc8` | `0x12f3394` | PC add `0x60dce6`，literal `0x60dd0c` |
| DisplayManager | `0x145d0f0` | `0x12f38b8` | 原 getter `0x6b90d4`，GOT slot `0x1273344` |
| 完成回调参数 | `0x145dbb8` | `0x12f4380` | PC add `0x6bf0aa`，literal `0x6bf0c8` |
| 完成回调 | `0x145dbc0` | `0x12f4388` | PC add `0x6bf0a2`，literal `0x6bf0c4` |
| 完成信号量 | `0x145dbc4` | `0x12f438c` | PC add `0x6bf36a`，literal `0x6bf3cc` |
| pViewManager | `0x149221c` | `0x13289f4` | 同名导出 |

Bitmap、纹理及 GL context vptr 通过原 RTTI 名称匹配，Bitmap 读锁和解锁 vtable 槽独立核对。实际 VM 已消费 raster、A8/Bitmap、LZ77、Gemini、slow clear、present 和 native completion 路径。未知格式仍拒绝。

## 原厂页面与输入

原 AP 的 `target=qemu` 启动停在 RootSelector。适配在原 UI 线程用 `ViewBase::openView` 顺序请求 `view/ROOT` 和 `view/STLREC`，由原 manager 创建和初始化页面。

RootSelector 的菜单接口子对象从 ZV-E10 的 `+0x154` 移到 A7M3 的 `+0x124`，由 RTTI 的 offset-to-top 确认。MENU 经原 `InputService::callback_convert` 发送按下和释放；当前 AP-only 根状态缺少完整 CP 事件推进，适配随后在原绘图线程调用 A7M3 自己的菜单 helper `viewUnified2+0x2bcfe1`。已经打开的菜单不会重复请求。此补偿必须与原始输入回调验证分开，不宣称原厂完整输入路由已恢复。

| 命令 | 原逻辑按下／释放 |
| --- | --- |
| MENU／返回 | `0x15010111`／`0x15010112`；返回另请求原关闭页面接口 |
| ENTER | `0x15010061`／`0x15010062` |
| DISP | `0x150101a1`／`0x150101a2` |

串口线程使用 Sony 原 `AMBAUART_IOC_SETMODE` 启用输入，并精确匹配命令及长度。未知命令不执行。所有状态通知仍来自实际帧，发送成功不等于界面已经接受。

## 图像区和帧导出

A7M3 拍摄页会提交 `0x32xxxxxx` 地址的图像，超出参考的 128 MiB 区间。QEMU 保留 `0x20000000..0x40000000`，软件映射及宿主取帧使用同一范围。拍摄页还提交带非线性布局标志的整面清屏；仅对覆盖完整表面、无混合、全不透明的均匀填充执行原字节效果，非线性局部绘图仍拒绝。

输出先等待原生产者完成，再取 Bitmap 读锁复制到页对齐的私有缓冲，pin 页面并发布实际 PFN、尺寸和摘要。保留最新及上一份完整快照，以覆盖 QMP 暂停落在下一次发布中途的情况。宿主暂停 QEMU 后排空已完成的发布，读取最新快照并校验 FNV，随后保存原生 RGBA4444、PNG 和 SHA256，再继续执行。

每次重取帧或像素内容变化都会发布最新内容，避免只保留资源尚未加载的第一帧。主机回归另验证内容变化、显式重取帧、读锁、完成通知、页边界、摘要拒绝和失败后恢复 QEMU。

## 验证边界

当前范围是本机启动、原生拍摄页面入口和 MENU 交互。原拍摄页中的快门、光圈、ISO 等模型值尚未完整恢复；原菜单可能提示“当前此功能无效”。原始失败、SID 设置页探针和 CAMERA 模型调查均保留在本地报告中。没有注册虚构的 CAMERA getter 响应，也没有以成功返回代替硬件状态。

测试入口为 `python3 tests/run-tests.py`。静态报告及早期 [host-checks.json](host-checks.json) 只描述各自检查范围；最终验收以项目 `validation/` 和最新报告为准。固件派生解码 fixture 不随仓库分发，缺少时相应用例明确 skip。
