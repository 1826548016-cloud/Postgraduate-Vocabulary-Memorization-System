# 考研单词背诵系统（1.1）版本
# 项目正在本人亲自测试中，欢迎反馈问题或建议。

基于 Django 的考研词汇背诵 Web 应用，支持词库管理、多模式背诵、模拟考试、学习统计与 AI 智能导入，开箱即用（SQLite 本地存储，无需外部数据库，如需使用其他数据库请自行在settings里面更改配置）。

## 功能特性

- **词库管理**
  - 单元（List）增删改查，单词完整增删改查（含音标、词性、多释义、熟词僻义、搭配、词形、例句）
  - 词汇类别：必考词 / 基础词 / 超纲词
  - 目前单词来源于考研界比较火的红宝书，本人亲自购买了一本并将里面部分单词使用ai导入到系统自行测试（未上线），仅供个人学习使用。并且为规范版权保护，完整词库不在上传，如有需要请自行购买红宝书上传进行自我使用。
  
- **背诵与复习**
  - 多模式背诵：顺序、乱序、遮英文、遮中文
  - 每次背诵实时更新单词状态（未掌握 / 已掌握）
  - 自动复习（艾宾浩斯复习计划）+ 手动复习 + 收藏复习

- **模拟考试**
  - 可配置考试范围、题数、考试方式
  - 干扰项从词库中随机抽取真实单词释义，不泄漏正确答案
  - 交卷后自动更新单词掌握状态

- **学习统计**
  - 学习趋势堆叠光滑折线图、正确率、每日打卡、新学/复习量统计

- **学习计划**
  - 每日新词数、每日复习量、目标日期、单元范围、剩余天数估算

- **收藏 / 笔记 / 专注模式** 等辅助功能

- **AI 智能导入**（`/ai-import/`）
  - 三种输入方式：**图片识别 / 纯文本 / 文件**（某些模型识别不了图片时可改用文本或文件）
  - 支持 20+ 模型服务商：OpenAI、Google Gemini、Anthropic Claude、xAI、通义千问、智谱 GLM、DeepSeek、Kimi等
  - 三级复审防错机制：
    1. **AI 复审**：调用 AI 核对单词拼写、音标、词性、释义是否正确，发现错误**自动修正**并弹出修正报告（如"已修正：aborign → aborigine"）
    2. **人工复审**：逐条核对，可手动编辑
    3. **随机抽审**：随机抽样再次核对
  - **大批量导入支持进度条 + 日志输出**：AI 复审按批（每批 20 个）执行，实时显示"第 k/N 批完成"及发现/修正统计，避免单次请求超时

- **数据安全**
  - 词库 JSON 备份 / 恢复（`backups/` 目录）
  - 词库 PDF 导出

## 技术栈

- Python 3.13 + Django 4.2.10
- SQLite（零配置）
- 原生 HTML / CSS / JS，ECharts 图表，Phonetic 在线发音

## 快速开始

```bash
# 1. 安装依赖
pip install django

# 2. 初始化数据库
python manage.py migrate

# 3.（可选）导入内置考研词库
python manage.py import_words data/hongbaoshu.json

# 4. 启动服务
python manage.py runserver
```

浏览器访问 <http://127.0.0.1:8000> 即可。


## AI 模型配置

1. 进入 `/ai-import/` 页面，点击「管理模型」→「添加模型」
2. 选择服务商 → 填写 API Key（部分本地服务可留空）→ 选择或填写模型 ID
3. 点击「测试连接」验证可用性
4. 模型配置保存在浏览器 `localStorage`



## 页面路由

| 路径 | 页面 |
| --- | --- |
| `/` | 仪表盘 |
| `/words/` | 词库管理 |
| `/words/<id>/` | 单词详情 |
| `/ai-import/` | AI 智能导入 |
| `/learn/` | 开始背诵 |
| `/learn/session/` | 背诵会话 |
| `/review/` | 复习会话 |
| `/exam/` | 模拟考试 |
| `/stats/` | 学习统计 |
| `/plan/` | 学习计划 |
| `/settings/` | 设置（字体/深色模式/发音） |
| `/favorites/` | 收藏列表 |
| `/focus/` | 专注模式 |

## 项目结构

```
d:\word
├── manage.py
├── vocab_project/          # Django 项目配置
│   ├── settings.py
│   └── urls.py
├── words/                  # 主应用
│   ├── models.py           # Unit / Word / StudyProgress / StudyPlan / StudySession 等
│   ├── views.py            # 页面视图 + 全部 API
│   ├── urls.py
│   ├── templates/          # HTML 模板
│   ├── static/             # CSS / JS / ECharts
│   └── management/commands/
│       ├── import_words.py # JSON 词库导入
│       └── import_text.py  # 纯文本导入
├── data/hongbaoshu.json    # 内置考研词库数据
├── backups/                # 备份文件目录
└── db.sqlite3              # 数据库
```

## 数据备份

- 页面内「导出备份」生成 JSON 到 `backups/` 目录，可随时「恢复备份」
- 也可直接复制 `db.sqlite3` 文件备份
