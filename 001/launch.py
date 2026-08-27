"""打包后的启动入口。

双击 exe 运行流程：
1. 切换工作目录到 exe 同目录（让 ./data/ 落地）
2. 配置 Django 环境
3. 首次启动：自动 migrate + 导入真题与词库
4. 启动 Django runserver（127.0.0.1:8000）
5. 自动打开默认浏览器
6. 主进程等待 Ctrl+C 退出

开发模式下也可以直接 `python launch.py` 跑（未打包时）。
"""
import os
import sys
import time
import threading
import webbrowser
from pathlib import Path

# PyInstaller 打包后，_MEIPASS 是解压的只读资源目录
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = Path(sys._MEIPASS)
    # 切换工作目录到 exe 同目录（便于 ./data/ 落地）
    os.chdir(Path(sys.executable).resolve().parent)
else:
    # 开发模式：launch.py 在 001/ 下，项目根在上一层
    BASE_DIR = Path(__file__).resolve().parent.parent
    os.chdir(BASE_DIR)

# 让 Python 能找到项目模块
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vocab_project.settings')

import django
django.setup()

from django.core.management import call_command
from django.conf import settings

DATA_DIR = Path(settings.DATA_DIR)
DB_PATH = DATA_DIR / 'db.sqlite3'


def first_run_init():
    """首次启动自动初始化数据（不含 API key，用户自行配置）"""
    print('=' * 56)
    print('  首次启动，正在初始化数据库…')
    print('=' * 56)

    call_command('migrate', interactive=False, verbosity=1)

    # 用 call_command 走 Django 框架，比直接 import 更可靠
    print('[初始化] 导入考研真题…')
    try:
        call_command('import_exam_questions', verbosity=0)
        print('  考研真题导入完成')
    except Exception as e:
        print(f'  考研真题导入失败：{e}')

    print('[初始化] 导入六级翻译真题…')
    try:
        call_command('import_cet6_translations', verbosity=0)
        print('  六级翻译导入完成')
    except Exception as e:
        print(f'  六级翻译导入失败：{e}')

    # 红宝书词库（若打包时带入了 data/hongbaoshu.json）
    hongbao = BASE_DIR / 'data' / 'hongbaoshu.json'
    if hongbao.exists():
        print('[初始化] 导入红宝书词库…')
        try:
            call_command('import_words', str(hongbao), verbosity=0)
            print('  红宝书词库导入完成')
        except Exception as e:
            print(f'  词库导入失败：{e}')

    print('=' * 56)
    print('  初始化完成！请到「设置」页配置 AI 模型后即可使用')
    print('=' * 56)


def main():
    # 首次启动自检
    if not DB_PATH.exists():
        first_run_init()
    else:
        # 即便 db 已存在，也确保 migrations 已应用（防止跨版本升级）
        call_command('migrate', interactive=False, verbosity=0)

    # 后台线程：2 秒后开浏览器
    def open_browser():
        time.sleep(2)
        try:
            webbrowser.open('http://127.0.0.1:8000/')
        except Exception:
            pass
    threading.Thread(target=open_browser, daemon=True).start()

    print('=' * 56)
    print('  考研英语学习平台已启动')
    print('  浏览器访问：http://127.0.0.1:8000/')
    print('  数据目录：' + str(DATA_DIR))
    print('  按 Ctrl+C 退出')
    print('=' * 56)

    # use_reloader=False：避免 PyInstaller 下双进程问题
    call_command('runserver', '127.0.0.1:8000', use_reloader=False)


if __name__ == '__main__':
    main()
