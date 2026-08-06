"""生成"仅词库"种子数据库，供 exe 打包使用。

用法：python make_seed_db.py
产出：packaging/db.sqlite3（保留全部词库，清空所有个人数据与 API Key）
"""
import os
import shutil
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE_DIR, 'db.sqlite3')
DST_DIR = os.path.join(BASE_DIR, 'packaging')
DST = os.path.join(DST_DIR, 'db.sqlite3')

# 个人 / 运行时数据表：打包前清空（保留表结构）
CLEAR_TABLES = [
    'words_aimodel',        # AI 模型配置（含 API Key）
    'words_chatmessage',    # 小助手对话
    'words_dailycheckin',   # 每日打卡
    'words_favorite',       # 收藏
    'words_importlog',      # 导入记录
    'words_note',           # 笔记
    'words_quickmemory',    # AI 速记
    'words_studyplan',      # 学习计划
    'words_studyprogress',  # 学习进度
    'words_studysession',   # 学习会话
    'words_usersettings',   # 用户设置
    'django_session',       # 会话
    'auth_user', 'auth_user_groups', 'auth_user_user_permissions',
    'auth_group', 'auth_group_permissions',
    'django_admin_log',
]


def main():
    if not os.path.exists(SRC):
        raise SystemExit('未找到 %s，请先在项目根目录运行' % SRC)
    os.makedirs(DST_DIR, exist_ok=True)
    shutil.copy2(SRC, DST)

    conn = sqlite3.connect(DST)
    cur = conn.cursor()
    for t in CLEAR_TABLES:
        cur.execute('DELETE FROM "%s"' % t)
    try:
        cur.execute('DELETE FROM sqlite_sequence')
    except sqlite3.OperationalError:
        pass  # 没有自增序列表，忽略
    conn.commit()

    kept = {
        t: cur.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        for t in ('words_unit', 'words_word')
    }
    conn.close()

    print('种子数据库已生成：%s' % DST)
    print('保留：%s' % kept)
    print('已清空个人数据与 API Key（共 %d 张表）' % len(CLEAR_TABLES))


if __name__ == '__main__':
    main()
