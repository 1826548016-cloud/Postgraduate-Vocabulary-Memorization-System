---
name: 考研单词背诵系统
description: 错题本 × 现代稳妥 —— 红笔批注的暖纸界面
colors:
  primary: "#c0392b"
  primary-hover: "#a93226"
  primary-deep: "#8f2b20"
  primary-bg: "#f7e7e3"
  blue-pen: "#3f6d9e"
  blue-pen-bg: "#e8eff6"
  stamp-amber: "#b7791f"
  stamp-amber-bg: "#f7efdc"
  master-green: "#4f7a58"
  master-green-bg: "#e9f0e6"
  study-purple: "#7b6b8f"
  study-purple-bg: "#f0ecf5"
  paper: "#f6f2e9"
  paper-card: "#fefcf7"
  paper-card-2: "#f1ecdf"
  ink: "#2b2721"
  ink-soft: "#6f6859"
  ink-faint: "#a49c8b"
  border-line: "#e4ddcc"
  border-line-light: "#eee8da"
  ink-sidebar: "#2e2922"
  on-primary: "#ffffff"
  sidebar-text: "#c9bfa4"
  sidebar-text-bright: "#f1ead6"
  sidebar-hover: "rgba(255,255,255,.07)"
  sidebar-divider: "rgba(255,255,255,.06)"
  night-bg: "#211d16"
  night-surface: "#2a251e"
  night-surface-2: "#342e24"
  night-text: "#e9e1d0"
  night-text-2: "#ab9f8a"
  night-text-3: "#7d7360"
  night-border: "#423a2c"
  night-red: "#e07a6b"
  night-red-bg: "#3a2925"
  night-blue: "#93b2d1"
  night-blue-bg: "#27303c"
  night-amber: "#d8a94f"
  night-amber-bg: "#3a301c"
  night-green: "#9dbb9f"
  night-green-bg: "#2b3527"
  night-purple: "#b6a5c7"
  night-purple-bg: "#342d3a"
typography:
  display:
    fontFamily: "'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', Georgia, serif"
    fontSize: "1.875rem"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', Georgia, serif"
    fontSize: "1.0625rem"
    fontWeight: 600
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
  caption:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 400
  micro:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "0.625rem"
    fontWeight: 400
  base:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
    fontSize: "1rem"
    fontWeight: 400
  phonetic:
    fontFamily: "'Times New Roman', serif"
    fontSize: "1.0625rem"
    fontWeight: 400
rounded:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  stamp: "4px"
  pill: "999px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  input-field:
    backgroundColor: "{colors.paper-card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "9px 12px"
  card-surface:
    backgroundColor: "{colors.paper-card}"
    rounded: "{rounded.md}"
    padding: "20px 24px"
---

# Design System: 考研单词背诵系统

## Overview

**Creative North Star: "The Correction Notebook / 错题本"**

系统把“备考背词”的界面想象成一页被红笔圈改过的作业纸：现代、克制的界面骨架（圆角、留白、清晰的层级）承载一种有温度的材质——暖纸底色、墨色文字、红笔批注。红笔是唯一的强强调色，蓝色圆珠笔是次级强调，就像一本真正被订正过的错题本；坚持与完成被表达成“印章”和“红笔填涂”，而不是霓虹与动效。

界面密度中等偏轻，信息优先，动效只用于表达状态。明暗双主题：白天是日光下的暖纸，夜间是台灯下的深色护眼纸。

**Key Characteristics:**
- 暖纸底 + 墨色文字 + 红笔红，三者构成主视觉关系
- 衬线标题（手写感）与无衬线正文的分工
- 纸感卡片：细边框 + 柔和暖阴影，圆角 12px
- 红笔稀缺：强调只给主操作、进度与关键状态
- 印章/批注是独有的签名元素，只在打卡与激励场景出现

## Colors

暖纸中性色是底，红笔红是声；语义色（蓝/绿/紫/琥珀）只承担各自的业务角色。

### Primary
- **红笔红** (#c0392b)：主操作按钮、主进度条、当前导航、红笔批注与印章。深色主题下为 #e07a6b 以保证对比度。

### Secondary
- **圆珠笔蓝** (#3f6d9e)：复习类信息与次级强调（复习进度、蓝笔批注）。深色 #93b2d1。

### Tertiary
- **印章琥珀** (#b7791f)：连续打卡、坚持类激励。深色 #d8a94f。
- **掌握绿** (#4f7a58)：已掌握/完成语义。深色 #9dbb9f。
- **复习紫** (#7b6b8f)：复习中/中性任务语义。深色 #b6a5c7。

### Neutral
- **暖纸** (#f6f2e9)：页面底色。深色 #211d16。
- **纸面卡** (#fefcf7)：卡片与浮层表面。深色 #2a251e。
- **墨色** (#2b2721)：正文。深色 #e9e1d0。
- **墨色弱** (#6f6859)：次级文字。深色 #ab9f8a。
- **墨色淡** (#a49c8b)：占位与说明。深色 #7d7360。
- **边框线** (#e4ddcc)：卡片边框。深色 #423a2c。
- **墨色侧栏** (#2e2922)：侧边导航底。深色 #1b1813。

### Named Rules
**The Red Pen Rule.** 红笔红只用于“行动与结果”——主按钮、进度、当前选中、批注、印章。任何界面中它出现的面积保持克制，泛用即贬值。

**The Two Pens Rule.** 红笔管“行动与结果”，蓝笔管“信息与复习”。不要让第三种强色抢走这两种笔的对话。

**Micro-palettes（有意保留的语义小色板，后续逐步令牌化）：** 词性标签家族（蓝/绿/橙/紫/青/青绿/红/灰，见 `.pos-tag-*`）与周历状态色（完成绿 #dcfce7/#86efac/#16a34a、今日琥珀 #fef3c7/#fcd34d/#d97706、错过红 #fef2f2/#fecaca/#dc2626）是已有业务语义的组成部分，不属于漂移；它们应被维持而非替换。

## Typography

**Display Font:** Noto Serif SC（回退 Source Han Serif SC / Songti SC / STSong / Georgia / serif）
**Body Font:** 系统无衬线栈（Segoe UI / PingFang SC / Microsoft YaHei）

**Character:** 衬线标题带一点手写与纸感，无衬线正文保证长内容可读；这对组合把“作业纸”的情绪压进标题层级，而不是撒到全页面。根字号固定 16px；移动端底部导航使用更小的 0.6rem 标签与 1.4rem 图标按钮，属导航专用尺度。

### Hierarchy
- **Display**（700，1.875rem，1.2）：仪表盘标语、卡片主数值（stat-value）、背诵卡单词（word-text）。
- **Title**（600，1.0625rem）：区块标题（card-header / section-title）、侧栏标识。
- **Body**（400，0.9375rem，1.6）：正文、表格、表单。
- **Label**（500，0.75rem）：统计标签、徽章、辅助说明。

### Named Rules
**The Two Hands Rule.** 衬线只做“展示”，无衬线只做“信息”。按钮、表单、标签、表格永远是无衬线；标题与数字可以衬线。

## Layout

侧边导航固定 220px（墨色），主内容区最大宽 1120px、内边距 28/32/48px。卡片栅格用 `auto-fill minmax(240px, 1fr)`，统计卡一行 5 列。间距节奏 8/16/24px：小组件用 8px，卡片间距 16px，区块间距 24px。断点 768px：侧栏折叠为底部横栏，统计卡与多列栅格收为单列。

## Elevation & Depth

暖阴影 + 细边框的混合：卡片以 1px 边框定型，以低透明度暖阴影（`0 1px 2px rgba(50,40,25,.05), 0 2px 8px rgba(50,40,25,.06)`）浮起；悬停升一级（`--shadow-md`）；模态与浮层用 `--shadow-lg`。深色主题阴影加深为黑色系。阴影承担“层级”，边框承担“轮廓”，两者不重复叠加。

## Shapes

卡片 12px 圆角，控件（按钮/输入）8px，小标签/小徽记 6px，背诵卡与大字卡 16px。徽章、日期胶囊、进度条、热力图例使用全圆角胶囊（999px）。红笔印章带轻微旋转（-3deg）、2px 红描边与 4px 圆角，是系统唯一的“手作”几何。热力图小格 2px、统计卡图标块 10px。边框统一 1px；禁用粗侧边色条（pos-group 已去除），强调靠背景色块与文字色。

## Components

### Buttons
- **Shape:** 圆角 8px（控件级）。
- **Primary:** 红笔红底（#c0392b）白字，hover 加深（#a93226），内边距 8px 18px。
- **Hover / Focus:** 0.15s 过渡；`:focus-visible` 绿色环（2px 偏移 2px）保证键盘可见——焦点环为绿色，避免与红色主操作冲突。
- **Secondary:** 透明底、墨色文字、1px 边框；hover 用浅纸面。
- **Danger:** 深红（#8f2b20），与主操作区分。

### Chips / Badges
- **Style:** 圆角胶囊，浅色底 + 语义色文字（红/蓝/琥珀/绿/紫），字号 0.75rem。
- **State:** 无选中态；仅作状态标签（new / learning / review / mastered）。

### Cards / Containers
- **Corner Style:** 12px。
- **Background:** 纸面卡（#fefcf7），深色 #2a251e。
- **Border:** 1px 边框线（#e4ddcc）。
- **Shadow Strategy:** 暖阴影，悬停升一级（见 Elevation）。
- **Internal Padding:** 20px 24px（移动端 16px 18px）。

### Inputs / Fields
- **Style:** 纸面底、1px 边框、8px 圆角；focus 时边框变红 + 3px 红色光晕（`0 0 0 3px rgba(63,92,69,.14)` 改为红系）。
- **Focus:** 边框红 + 光晕；键盘焦点不叠加外环。
- **Error / Disabled:** 红色语义；disabled 40% 不透明度。

### Navigation
- 墨色侧栏（#2e2922），导航文字纸色；active 为红笔浅底（#f7e7e3）+ 红字，不再使用侧边色条。移动端折叠为底部横栏。

### Signature Component: The Stamp（红笔印章）
打卡/连续天数使用双红描边、轻微旋转的印章胶囊（2px 红边、-3deg、字母间距），在仪表盘标语区出现；它是“错题本”世界最独特的可识别元素。

## Do's and Don'ts

### Do:
- **Do** 把红笔红留给主操作、主进度、当前选中、批注与印章。
- **Do** 用暖纸中性色做底，让红色与蓝色笔在纸面上说话。
- **Do** 标题/数值用衬线，正文/控件用无衬线。
- **Do** 保持 8/16/24px 的间距节奏与 12px 卡片圆角。
- **Do** 在打卡与激励场景使用印章元素。

### Don't:
- **Don't** 把绿色当主强调色（它是“完成”语义，不是主操作）。
- **Don't** 使用粗侧边色条（border-left >1px）强调卡片或列表。
- **Don't** 让红笔红大面积铺开——稀缺是它的力量。
- **Don't** 回到“暖纸书卷”的墨绿 + 砖红配对（旧世界的反参考）。
- **Don't** 用渐变文字、玻璃拟态或霓虹发光表达激励。
