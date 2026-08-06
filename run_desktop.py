"""考研单词桌面版启动入口（打包 exe 用）

双击 exe 后：
1. 把数据库、备份、媒体等用户数据放到可写目录（默认 %APPDATA%/VocabApp）
2. 用 waitress 在本地启动 Django，并自动打开默认浏览器
3. 关闭本窗口即可退出程序
"""
import os
import shutil
import socket
import sys
import threading
import webbrowser


def resource_path(rel):
    """打包后资源在 _MEIPASS，开发时就在项目根目录"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def get_data_dir():
    """用户数据目录：可写、升级不丢"""
    d = os.environ.get('VOCAB_DATA_DIR')
    if not d:
        d = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'VocabApp')
    os.makedirs(d, exist_ok=True)
    return d


def first_run_setup(data_dir):
    """首次运行：把内置数据库复制到数据目录"""
    dst_db = os.path.join(data_dir, 'db.sqlite3')
    if not os.path.exists(dst_db):
        src_db = resource_path('db.sqlite3')
        if os.path.exists(src_db):
            shutil.copy2(src_db, dst_db)
    for sub in ('backups', 'media'):
        os.makedirs(os.path.join(data_dir, sub), exist_ok=True)


def find_free_port(start=8010):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vocab_project.settings')
    data_dir = get_data_dir()
    os.environ['VOCAB_DATA_DIR'] = data_dir
    os.environ['VOCAB_APP_DIR'] = resource_path('.')

    first_run_setup(data_dir)

    import django
    django.setup()

    from django.core.management import call_command
    call_command('migrate', verbosity=0, interactive=False)

    # DEBUG 模式下用 StaticFilesHandler 让 waitress 也能正常提供 /static/ 资源
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from waitress import serve
    from vocab_project.wsgi import application

    app = StaticFilesHandler(application)
    port = find_free_port()
    url = 'http://127.0.0.1:%d/' % port
    if not os.environ.get('VOCAB_NO_BROWSER'):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    print('=' * 46)
    print('  考研单词助手已启动')
    print('  地址：%s' % url)
    print('  关闭本窗口即可退出程序')
    print('=' * 46)
    serve(app, host='127.0.0.1', port=port, threads=8)


if __name__ == '__main__':
    main()
