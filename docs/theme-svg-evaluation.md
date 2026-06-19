# EcoMonitor 深色主题与 SVG 图标方案评估

**评估日期**：2026-06-19  
**评估范围**：`src/gui/` 视觉层、`src/gui/constants.py`、`src/gui/styles.py`、打包配置  
**目标**：从可行性、风险、实现成本三个维度评估深色主题与 SVG 图标方案，并给出分阶段落地建议。

---

## 1. 当前基础

经过 P1 优化，项目已具备以下设计系统基础：

- `src/gui/constants.py` 集中管理颜色、字号、间距、状态色等 Token。
- `src/gui/styles.py` 提供 `get_global_stylesheet()` 统一生成全局 QSS。
- 主窗口、连接页、终端页等已改用 `objectName` 或 `Color` / `StatusColor` 常量。
- `src/utils/config.py` 支持配置持久化，可新增 `ui.theme` 等配置项。

这些基础为深色主题和图标替换提供了可行的入口，但仍有不少内联样式和硬编码色值需要进一步迁移。

---

## 2. 深色主题方案评估

### 2.1 实现方式对比

| 方案 | 实现思路 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|---|
| **A. QPalette 轻量方案** | 通过 `QApplication.setPalette()` 设置全局调色板，配合少量 QSS 覆盖控件 | 改动小、与系统主题可联动、性能最好 | 对复杂自定义控件控制有限，部分 Qt 样式忽略 Palette | ⭐⭐⭐ |
| **B. 全量 QSS 动态生成方案** | 在 `styles.py` 中维护 light/dark 两套 Token，运行时根据主题重新生成 QSS 并 `setStyleSheet` | 控制力强，可实现高度一致的深色视觉 | 工作量大，需要替换所有剩余硬编码颜色；动态切换需要重绘所有窗口 | ⭐⭐⭐⭐ |
| **C. 混合方案（推荐）** | 用 `QPalette` 处理基础控件（按钮、输入框、表格、菜单），用动态 QSS 处理标签页、视频窗格、日志面板等自定义区域 | 兼顾开发效率与视觉一致性；对现有代码侵入适中 | 仍需要统一剩余硬编码颜色 | ⭐⭐⭐⭐⭐ |
| **D. 系统主题自动跟随** | 监听 Windows 注册表或 `QStyleHints.colorScheme()`，自动切换 | 用户体验最好 | Qt 6.5+ 才提供稳定 API，3.8 环境受限；自动切换可能不符合监控场景需求 | ⭐⭐⭐ |

### 2.2 关键风险

1. **视频预览区域冲突**
   - 深色主题下全局背景变暗，但 `VideoWidget` 当前背景是 `#1a1a1a`（已经接近深色），切换时问题不大。
   - 风险点：未播放状态、加载状态、错误提示文字颜色需要确保在深色背景下可读。

2. **剩余硬编码颜色**
   - 经过 P1 仍有约 77 处 `setStyleSheet` 调用，部分使用 `#fff`、`#ffffff`、`#000` 等写死颜色。
   - 如果不迁移，深色主题下会出现“白底黑字撕裂”或“黑底黑字看不见”。

3. **图表与曲线**
   - `speedtest_tab.py` 中的 `SpeedCurveWidget` 使用固定颜色绘制曲线和网格。
   - 深色模式下需要动态调整曲线颜色、坐标轴文字、背景色。

4. **终端区域**
   - 终端输出已使用 `QTextEdit#terminal` 全局样式（黑底浅灰字），天然适合深色主题，但切换时仍需保持一致。

5. **图片/图标资源**
   - 如果后续引入 SVG 图标，图标颜色需要随主题变化；否则深色背景下黑色图标会消失。

6. **PyInstaller 打包**
   - 新增主题资源文件需要在 `main.spec` 的 `datas` 中注册。
   - 动态 QSS 不依赖外部资源，风险较低。

### 2.3 推荐方案：混合方案 C

**阶段一：主题 Token 层**
- 新增 `src/gui/theme.py`：
  - `Theme` 枚举：`LIGHT`、`DARK`、`SYSTEM`。
  - `ThemeColors` 数据类：定义 `background`、`surface`、`panel`、`text_primary`、`text_secondary`、`border`、`primary`、`success`、`warning`、`error` 等角色。
  - `ThemeManager`：根据配置或系统主题返回当前 `ThemeColors`，并提供 `apply_to_app(app)` 方法。
- 修改 `src/gui/constants.py`：
  - 将 `Color` 类从“静态色值”改为“主题色角色占位”，或保留 `Color` 作为 fallback，新增 `ThemeColor` 角色层。
  - 建议：**保留 `Color` 常量用于语义别名，但 `styles.py` 不再直接引用 `Color.GRAY_xxx`，而是引用 `ThemeManager.current().text_secondary` 等角色。**

**阶段二：QSS 动态化**
- `src/gui/styles.py` 中 `MAIN_WINDOW`、`VIDEO_WIDGET` 等不再使用 `Color` 常量，而是接收 `theme_colors` 参数生成。
- `MainWindow._apply_styles()` 根据 `config.get("ui.theme")` 重新生成 QSS。
- 对动态状态色（`StatusColor`）提供深色模式下的对应值，例如：
  - `online` 在浅色下用 `#107c10`，在深色下用 `#2ecc71`（更亮）。
  - `offline` 在深色下用 `#888888`。

**阶段三：QPalette 兜底**
- 在 `ThemeManager.apply_to_app()` 中设置 `QPalette`：
  - `Window`、`Base`、`Button`、`Text`、`Highlight` 等角色映射到主题 Token。
- 这样即使某些控件未覆盖到 QSS，也不会出现大白底。

**阶段四：图表适配**
- `SpeedCurveWidget.paintEvent()` 中颜色改为从 `ThemeManager.current()` 读取。
- 网格线、文字、填充色都按主题切换。

**阶段五：配置入口与切换**
- 在 `设置 -> 外观` 中增加主题下拉框：浅色 / 深色 / 跟随系统。
- 切换时调用 `ThemeManager.apply_to_app(QApplication.instance())` 并刷新全局 QSS。
- 主题配置写入 `ui.theme`。

### 2.4 工作量预估

| 阶段 | 预估工时 | 主要文件 |
|---|---|---|
| 阶段一：Token 层 | 0.5 人天 | `src/gui/theme.py`、`src/gui/constants.py` |
| 阶段二：QSS 动态化 | 1.5 人天 | `src/gui/styles.py`、`src/gui/main_window.py` |
| 阶段三：QPalette 兜底 | 0.5 人天 | `src/gui/theme.py` |
| 阶段四：图表适配 | 0.5 人天 | `src/gui/tabs/speedtest_tab.py` |
| 阶段五：配置入口 | 0.5 人天 | `src/gui/main_window.py`、`src/utils/config.py` |
| 回归测试 | 1 人天 | 所有标签页 |
| **合计** | **约 4.5 人天** | — |

### 2.5 是否现在实施的建议

**建议暂缓全面实施**，原因：
- 当前仍有大量内联样式未迁移，直接做深色主题会放大撕裂风险。
- 深色主题对监控类软件的收益主要是“夜间使用”，但用户核心诉求是功能完整可用性。
- 可以在完成剩余内联样式迁移后，再作为一个独立版本（如 v1.1.0）实施。

**建议现在做的工作**：
- 完成 `src/gui/theme.py` 与 Token 设计（阶段一），作为基础设施先行。
- 在 `styles.py` 中预留 `theme_colors` 参数，不破坏现有浅色主题。

---

## 3. SVG 图标方案评估

### 3.1 实现方式对比

| 方案 | 实现思路 | 优点 | 缺点 | 推荐度 |
|---|---|---|---|---|
| **A. 图标字体（如 Segoe Fluent Icons / Material Icons）** | 把图标当作文字使用 `QLabel`/`QPushButton` 的 `font-family` | 矢量、缩放无损、颜色通过 QSS 控制、不增加打包文件 | 依赖系统字体或需要分发字体文件；图标语义不够直观 | ⭐⭐⭐⭐ |
| **B. 独立 SVG 文件 + QSvgRenderer** | 在 `assets/icons/` 放 SVG，用 `QSvgRenderer` 绘制到 `QPixmap` | 标准做法；图标可独立更新；颜色可通过 CSS `fill` 控制 | 需要处理高 DPI、路径查找、打包纳入、缺失 fallback | ⭐⭐⭐⭐ |
| **C. Qt 资源系统（.qrc）** | 把 SVG 编译进 `.py` 资源模块，通过 `:/icons/xxx.svg` 引用 | 打包最干净，无需担心路径 | 增加构建步骤（`pyrcc6` / `pyqt6-rcc`）；图标更新需重新编译 | ⭐⭐⭐ |
| **D. 内嵌 SVG 字符串** | 直接把 SVG XML 写在 Python 常量里 | 无需外部文件 | 代码臃肿；不易维护 | ⭐⭐ |

### 3.2 关键风险

1. **打包路径**
   - 使用 SVG 文件时，`pyinstaller` 不会自动打包 `assets/icons/`，必须在 `main.spec` 的 `datas` 中显式加入。
   - 使用 Qt 资源系统时，`pyinstaller` 需要把生成的 `_rc.py` 加入 `hiddenimports`。

2. **高 DPI 适配**
   - 监控软件常在 4K 大屏运行，图标需要支持多倍缩放。
   - SVG 天然支持，但需要确保 `QSvgRenderer` 在高分屏下渲染清晰。

3. **主题色联动**
   - SVG 默认颜色通常是黑色，深色主题下会看不清。
   - 如果使用 SVG 文件，需要两套图标（浅色/深色），或在 SVG 中移除固定填充、通过 QSS 控制 `fill`。
   - 图标字体方案通过 `color` 属性即可联动主题，最为方便。

4. **网络运维工具的直观性**
   - 当前使用纯文字标签（如“设备搜索”），专业且稳定。
   - 图标应作为辅助，不能替代文字；否则新用户学习成本上升。

5. **工具链依赖**
   - 使用 Qt 资源系统需要 `pyrcc6` 或 `pyqt6-rcc`，当前 `requirements.txt` 未包含 `PyQt6-tools`。
   - 使用 `QSvgRenderer` 需要 `PyQt6.QtSvg`，需确认是否已随 `PyQt6` 安装（通常已包含）。

### 3.3 推荐方案：图标字体优先 + SVG 为辅

**主方案 A：图标字体**
- 使用系统自带的 **Segoe Fluent Icons**（Windows 10/11 自带）或 **Segoe MDL2 Assets**。
- 对按钮/菜单增加一个 `QLabel` 图标 + 文字布局，图标通过 `font-family: "Segoe Fluent Icons"` 设置。
- 优点：
  - 不增加任何文件。
  - 颜色、大小完全由 QSS 控制，天然支持深色主题。
  - 在 Windows 目标机器上字体通常存在。
- 缺点/缓解：
  - 老版本 Windows（如 Windows 7）可能无此字体 → 降级为纯文字（保留当前文字）。
  - 图标语义不直观 → 必须保留文字，图标仅作装饰。

**辅方案 B：SVG 文件**
- 对极少数复杂图标（如自定义状态指示灯），可引入极简 SVG。
- SVG 要求：
  - 移除固定 `fill`，使用 `currentColor` 或空白填充。
  - 通过 QSS 的 `color` 或 `qproperty-icon` 控制颜色。
  - 打包时纳入 `assets/icons/`。

**不推荐现在使用 Qt 资源系统（方案 C）**，除非项目后期图标数量激增；当前引入会增加构建复杂度，收益不明显。

### 3.4 工作量预估

| 阶段 | 预估工时 | 主要工作 |
|---|---|---|
| 图标字体接入 | 0.5 人天 | 新增 `src/gui/icons.py` 常量，封装图标字体工具函数 |
| 主窗口/标签页图标替换 | 1 人天 | 为标签页、工具栏按钮增加图标 + 文字布局 |
| 状态图标替换 | 0.5 人天 | 用字体图标替代剩余文字符号（如 ⚠️ 类） |
| 打包与回归 | 0.5 人天 | 验证 PyInstaller 打包后图标正常 |
| **合计** | **约 2.5 人天** | — |

### 3.5 是否现在实施的建议

**建议先于深色主题实施**，原因：
- 工作量小于深色主题。
- 图标字体方案风险低，不引入外部文件，且能立即提升 UI 专业感。
- 为后续深色主题打下“颜色可控图标”的基础。

**建议现在做的工作**：
- 新增 `src/gui/icons.py`，定义常用图标 Unicode 与图标字体工具函数。
- 在主窗口标签页和关键按钮上小范围试点图标 + 文字。
- 收集用户反馈后再推广到全界面。

---

## 4. 综合优先级与路线图

```
当前（v1.0.x）
  │
  ├─ 完成剩余内联样式迁移（P1 后续）
  │
  ├─ 图标字体试点（P3-1，约 2.5 人天）
  │     └─ 新增 src/gui/icons.py
  │     └─ 主窗口标签页图标 + 文字
  │     └─ 验证打包
  │
  └─ 主题 Token 先行（P3-2，约 0.5 人天）
        └─ 新增 src/gui/theme.py
        └─ styles.py 预留 theme_colors 参数

下一版本（v1.1.0）
  │
  └─ 完整深色主题（P3-3，约 4 人天）
        └─ QPalette + 动态 QSS
        └─ 图表颜色动态化
        └─ 设置入口
```

---

## 5. Python 3.10 升级后的实际观察与调整

在完成 Python 3.10 升级并实际跑通 PyInstaller 打包后，对深色主题 / SVG 图标方案有以下补充观察：

### 5.1 PyInstaller 6.21 + Python 3.10 打包验证结果

- PyInstaller 6.21.0 在 Python 3.10.11 下可正常完成打包。
- `post_build_cleanup.py` 清理后节省约 **127.5 MB** 空间，主题/图标引入的额外体积可控。
- 打包产物中 `numpy` 与 `numpy.libs` 已正确纳入 `_internal/`，视频解码功能不会缺失。

### 5.2 对主题/图标实现的影响

1. **新增模块必须加入 hiddenimports**
   - 实际发现：`src.core.player.video_decoder` 因未被入口文件直接导入，即使 `numpy` 不在 excludes 中，PyInstaller 也不会自动收集。
   - 因此，新增 `src/gui/theme.py`、`src/gui/icons.py` 等模块后，必须在 `build/main.spec` 的 `hiddenimports` 中显式声明，否则打包产物中会缺失。

2. **图标字体打包风险最低**
   - 图标字体完全依赖系统字体和 QSS `font-family`，不引入额外文件，不需要修改 `main.spec` 的 `datas` 或 `hiddenimports`。
   - 这进一步巩固了“图标字体优先”的推荐结论。

3. **SVG 文件需要 datas 注册**
   - 如果选择 SVG 文件方案，必须在 `main.spec` 的 `datas` 中加入 `assets/icons/`。
   - 同时需确认 `PyQt6.QtSvg` 被正确打包（通常 PyInstaller 会自动收集，但建议在 `hiddenimports` 中显式加入以保险）。

4. **QPalette 方案的打包友好性**
   - QPalette 纯代码实现，不依赖外部资源，对 PyInstaller 打包无额外影响。
   - 动态 QSS 方案也不依赖外部资源，但生成函数需要在打包时被收集。

### 5.3 更新后的推荐结论

- **图标字体**：风险最低、打包零成本、与深色主题联动最简单，建议作为 P3 首选立即试点。
- **深色主题**：仍建议分阶段，但在 Python 3.10 环境已验证可打包，实施障碍降低。
- **SVG 文件**：可作为辅助，但需额外处理 datas 注册和颜色联动，优先级低于图标字体。

---

## 6. 结论

- **深色主题**：技术可行，推荐“QPalette + 动态 QSS”混合方案；但当前不宜全面实施，建议先完成内联样式迁移并建立主题 Token。
- **SVG 图标**：推荐 **图标字体优先、SVG 文件为辅** 的方案，工作量较小、风险低、与深色主题兼容性好。
- **下一步建议**：
  1. 如资源允许，先做图标字体试点（2.5 人天），同时把 `src.gui.icons` 加入 `main.spec` 的 `hiddenimports`。
  2. 同时完善剩余内联样式迁移。
  3. 待样式层稳定后，再用已建立的主题 Token 实施深色主题，并把 `src.gui.theme` 加入 `main.spec` 的 `hiddenimports`。
- **SVG 图标**：推荐 **图标字体优先、SVG 文件为辅** 的方案，工作量较小、风险低、与深色主题兼容性好。
- **下一步建议**：
  1. 如资源允许，先做图标字体试点（2.5 人天）。
  2. 同时完善剩余内联样式迁移。
  3. 待样式层稳定后，再用已建立的主题 Token 实施深色主题。

---

*评估结束。*
