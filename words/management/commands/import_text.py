"""
管理命令：从纯文本格式导入单词到指定单元
用法：python manage.py import_text <单元编号> [单元名称]
从标准输入读取文本数据
"""
import json
import sys
import re
from django.core.management.base import BaseCommand
from words.models import Unit, Word


def parse_entry(line_iter):
    """解析一个单词条目，返回 (word, phonetic, pos, meanings) 或 None"""
    # 跳过空行
    for line in line_iter:
        line = line.rstrip('\n').rstrip('\r')
        if not line.strip():
            continue
        break
    else:
        return None

    # 匹配条目: "N. word /phonetic/"  或  "N. word(var) /phonetic/"
    m = re.match(r'^(\d+)\.\s*(.+?)\s*/([^/]+)/\s*$', line)
    if not m:
        return None
    
    word_text = m.group(2).strip()
    phonetic = '/' + m.group(3).strip() + '/'
    
    # 收集词性+释义行
    pos_parts = []
    for next_line in line_iter:
        next_line = next_line.rstrip('\n').rstrip('\r')
        if not next_line.strip():
            break
        # 检查是否是下一个单词的起始（数字开头）
        if re.match(r'^\d+\.\s', next_line):
            # 把这一行放回去？我们不能放回，但可以让调用者处理
            # 检查它是否是下一个单词
            # 如果是，就停止
            # 标记：用sentinel
            # 简单方法：判断是否有 "/" 表示下一个单词
            if '/' in next_line:
                # 这应该是下一个单词
                break
        pos_parts.append(next_line.strip())
    
    if not pos_parts:
        return None
    
    # 解析词性+释义
    pos = ''
    meanings = []
    for part in pos_parts:
        # 匹配 "pos. 释义" 或 "pos. 释义; 释义2; 释义3"
        pm = re.match(r'^([a-z]+(?:/[\w]+)?\.?)\s*(.*)', part)
        if pm:
            p = pm.group(1).strip()
            m_text = pm.group(2).strip()
            if pos:
                pos += '/'
            pos += p
            if m_text:
                # 按中文分号或逗号分割
                m_list = re.split(r'[；;]', m_text)
                for m_item in m_list:
                    m_item = m_item.strip()
                    if m_item and not any(c.isalpha() for c in m_item):
                        continue  # skip pure symbols/punctuation
                    if m_item:
                        meanings.append(m_item)
    
    if not pos:
        pos = 'v.'
    
    return (word_text, phonetic, pos, meanings)


def parse_text(text):
    """解析完整文本，返回单词列表"""
    words = []
    lines = text.split('\n')
    n = len(lines)
    i = 0

    while i < n:
        raw = lines[i]
        i += 1

        # 跳过空行、标题行
        if not raw.strip():
            continue
        if raw.lstrip().startswith('#'):
            continue
        if raw.startswith('---'):
            continue

        m = re.match(r'^(\d+)\.\s+(.+?)\s*/([^/]+)/\s*$', raw)
        if not m:
            continue

        word_text = m.group(2).strip()
        phonetic = '/' + m.group(3).strip() + '/'

        # 收集后续的词性释义行
        pos_parts = []
        while i < n:
            nxt = lines[i].rstrip('\n').rstrip('\r')
            if not nxt.strip():
                i += 1
                break
            # 检测下一个单词条目
            if re.match(r'^\d+\.\s+.+?/.*/', nxt):
                break
            pos_parts.append(nxt.strip())
            i += 1

        # 解析词性 + 释义
        pos = ''
        meanings = []
        for part in pos_parts:
            pm = re.match(r'^([a-zA-Z]+(?:/[\w]+)?\.?)\s*(.*)', part)
            if pm:
                p = pm.group(1).strip()
                m_text = pm.group(2).strip()
                if pos:
                    pos += '/'
                pos += p
                if m_text:
                    for m_item in re.split(r'[；;]', m_text):
                        m_item = m_item.strip()
                        if m_item:
                            meanings.append(m_item)
            else:
                for m_item in re.split(r'[；;]', part):
                    m_item = m_item.strip()
                    if m_item:
                        meanings.append(m_item)

        if not pos:
            pos = 'v.'

        words.append((word_text, phonetic, pos, meanings))

    return words


class Command(BaseCommand):
    help = '从纯文本格式导入单词到指定单元'

    def add_arguments(self, parser):
        parser.add_argument('unit_number', type=int, help='单元编号')
        parser.add_argument('--name', type=str, default='', help='单元名称')
        parser.add_argument('--category', type=str, default='required',
                          choices=['required', 'basic', 'advanced'], help='词汇类别')
        parser.add_argument('--clear', action='store_true', help='导入前清空该单元现有单词')

    def handle(self, *args, **options):
        unit_number = options['unit_number']
        unit_name = options['name'] or f'List {unit_number}'
        category = options['category']
        clear = options['clear']

        # 读取标准输入
        text = sys.stdin.read()
        if not text.strip():
            raise CommandError('没有输入数据！请通过管道传入文本。')

        words = parse_text(text)
        if not words:
            raise CommandError('未能解析出任何单词，请检查输入格式。')

        self.stdout.write(f'解析到 {len(words)} 个单词')

        # 获取或创建单元
        unit, created = Unit.objects.get_or_create(
            number=unit_number,
            defaults={'name': unit_name, 'category': category}
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'创建单元: {unit_name}'))
        else:
            # 更新名称
            if not options['name']:
                pass  # 保持现有名称
            else:
                unit.name = unit_name
                unit.category = category
                unit.save()
            self.stdout.write(f'使用已有单元: {unit.name}')

        if clear:
            deleted, _ = Word.objects.filter(unit=unit).delete()
            self.stdout.write(self.style.WARNING(f'清除了 {deleted} 个旧单词'))

        # 导入单词
        total = 0
        skipped = 0
        for i, (word_text, phonetic, pos, meanings) in enumerate(words, 1):
            existing = Word.objects.filter(word__iexact=word_text).first()
            if existing:
                if existing.unit != unit:
                    self.stdout.write(self.style.WARNING(
                        f'单词 "{word_text}" 已存在于 List {existing.unit.number}，跳过'))
                else:
                    self.stdout.write(self.style.WARNING(f'跳过重复: {word_text}'))
                skipped += 1
                continue

            Word.objects.create(
                word=word_text,
                phonetic_us=phonetic,
                phonetic_uk=phonetic,
                pos=pos,
                meanings=json.dumps(meanings, ensure_ascii=False),
                category=category,
                unit=unit,
                list_number=i,
            )
            total += 1

        # 更新单元词数
        unit.word_count = unit.words.count()
        unit.save()

        self.stdout.write(self.style.SUCCESS(
            f'\n导入完成！\n'
            f'  单元: {unit.name}\n'
            f'  导入: {total} 个单词\n'
            f'  跳过: {skipped} 个'
        ))
