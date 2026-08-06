# -*- mode: python ; coding: utf-8 -*-
"""考研单词桌面版 PyInstaller 打包配置

构建命令（在项目根目录执行）：
    pyinstaller vocab_app.spec --noconfirm
产物目录：dist/VocabApp/
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

datas = [
    ('words/templates', 'words/templates'),
    ('words/static', 'words/static'),
    ('data/hongbaoshu.json', 'data'),
    # 打包前先运行 python make_seed_db.py 生成"仅词库"种子数据库
    ('packaging/db.sqlite3', '.'),
]
# reportlab 需要字体/CMap 等数据文件；admin 需要模板和静态资源
datas += collect_data_files('reportlab')
datas += collect_data_files('django.contrib.admin')
datas += collect_data_files('django.contrib.auth')

hiddenimports = [
    'django.template.defaultfilters',
    'django.template.loader',
    'django.template.backends.django',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.core.management.commands.migrate',
    'django.db.backends.sqlite3',
]
hiddenimports += collect_submodules('words')
hiddenimports += collect_submodules('reportlab')

a = Analysis(
    ['run_desktop.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VocabApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VocabApp',
)
