# 考研英语学习平台

Windows 单文件版，双击即用，无需安装 Python 或任何依赖。

## 快速开始

1. 把 `dist/word.exe` 复制到任意目录（如桌面）
2. 双击 `word.exe`
   - 首次启动约 10-20 秒（自动建表 + 导入考研真题、六级翻译、红宝书词库）
   - 之后每次启动 3-5 秒
3. 浏览器会自动打开 `http://127.0.0.1:8000/`
   - 没自动打开就手动访问这个地址
4. **第一次使用请到「设置」页配置 AI 模型**（填入 API key）
   - 词汇背诵、真题浏览、学习统计等核心功能开箱即用，无需配置
   - AI 代写、AI 批改、AI 速记等 AI 功能必须配 key 才能用
5. 用完按 `Ctrl+C` 退出（直接关黑窗口也行）

## 数据存哪里

所有数据都在 `word.exe` 同目录的 `./data/` 文件夹：

| 路径 | 内容 |
|---|---|
| `./data/db.sqlite3` | 数据库（词汇进度、练习记录、AI 模型配置等） |
| `./data/media/` | 用户上传的 PDF、音乐等 |
| `./data/backups/` | 备份文件 |

- **换电脑**：把 `word.exe` 和 `./data/` 一起复制走即可
- **清空重来**：删掉 `./data/` 文件夹，下次启动会重新初始化
- **别把 `db.sqlite3` 发给别人**：里面有你自己的 API key

## 安全说明

- 打包产物**不含 API key**：exe 是空的，启动后由你自己配置
- 你在「设置」页填的 key 只存在本地 `./data/db.sqlite3`，不会上传任何地方
- 把 `word.exe` 发给别人时不会泄露你的 key

## 常见问题

**Q: 启动报「端口 8000 被占用」？**
A: 已有程序占用了 8000 端口。关掉占用端口的程序，或改 `launch.py` 末尾的 `127.0.0.1:8000` 为其他端口后重新打包。

**Q: 杀毒软件报毒？**
A: PyInstaller 打的 exe 常被误报。把 `word.exe` 加入白名单即可，不影响使用。

**Q: 首次启动卡很久？**
A: 正在导入题库，约 10-20 秒，等控制台打印「初始化完成」即可。

**Q: 浏览器没自动打开？**
A: 手动访问 `http://127.0.0.1:8000/`。

---

## 重新打包（开发者）

源码在项目根 `d:\word\`，打包配置在 `d:\word\001\`。

```powershell
cd d:\word\001
.\build.ps1
```

或手动：
```powershell
pip install pyinstaller
pip install -r d:\word\requirements.txt
cd d:\word\001
pyinstaller word.spec --noconfirm
```

产物：`d:\word\001\dist\word.exe`

### 文件说明

| 文件 | 作用 |
|---|---|
| `dist/word.exe` | 打包产物，可分发 |
| `launch.py` | 启动入口：自检 db → migrate → 导入真题 → runserver → 开浏览器 |
| `word.spec` | PyInstaller 配置：onefile + 控制台 + 资源收集 |
| `build.ps1` | 一键打包脚本 |

### 自定义

- **加图标**：放 `icon.ico` 到 `001/`，把 `word.spec` 里 `icon=None` 改成 `icon='icon.ico'`
- **加 ffmpeg**（音乐播放器需要）：放 `ffmpeg.exe`、`ffprobe.exe` 到 `word.exe` 同目录，启动会自动检测
- **改端口**：改 `launch.py` 末尾 `call_command('runserver', '127.0.0.1:8000', ...)`
