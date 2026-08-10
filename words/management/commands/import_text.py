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
from words.views import normalize_word_data, ai_complete_words

# 单词条目行： "N. word /phonetic/"  或  "N. word(var) /phonetic/"  或  "N. word"（无音标）
WORD_LINE_RE = re.compile(r'^\s*(\d+)\.\s+(.+?)\s*$')
# 行内音标：末尾 /.../
PHONETIC_RE = re.compile(r'^(.*?)\s*/([^/]+)/\s*$')
# 下一个单词条目行的判定：数字开头 + 单词 + 可选音标
NEXT_WORD_RE = re.compile(r'^\d+\.\s+[^\s/]+(?:\s*/.+/)?\s*$')


def _norm_pos_label(p):
    """规范化词性标签：小写 + 补全末尾点号（v → v.，adj → adj.）"""
    p = str(p).strip().lower()
    if not p:
        return p
    if p[-1] != '.':
        p += '.'
    return p


def parse_text(text):
    """解析完整文本，返回单词字典列表（随后统一走 normalize_word_data 规范化）"""
    words = []
    lines = text.split('\n')
    n = len(lines)
    i = 0

    while i < n:
        raw = lines[i].rstrip('\r')
        i += 1

        # 跳过空行、标题行
        if not raw.strip():
            continue
        if raw.lstrip().startswith('#'):
            continue
        if raw.startswith('---'):
            continue

        m = WORD_LINE_RE.match(raw)
        if not m:
            continue

        word_field = m.group(2).strip()
        phonetic = ''
        pm = PHONETIC_RE.match(word_field)
        if pm and pm.group(1).strip():
            word_text = pm.group(1).strip()
            phonetic = pm.group(2).strip()
        else:
            word_text = word_field

        # 收集后续的词性释义行
        pos_parts = []
        while i < n:
            nxt = lines[i].rstrip('\r')
            if not nxt.strip():
                i += 1
                break
            # 检测下一个单词条目（数字开头 + 单词 + 可选音标），避免把释义行误判为下一个单词
            if NEXT_WORD_RE.match(nxt):
                break
            pos_parts.append(nxt.strip())
            i += 1

        # 解析词性 + 释义（按词性分组）
        pos = ''
        meanings = []
        meanings_by_pos = {}
        for part in pos_parts:
            pm = re.match(r'^([a-zA-Z]+(?:/[\w]+)?\.?)\s*(.*)', part)
            if pm:
                p = pm.group(1).strip()
                m_text = pm.group(2).strip()
                if pos:
                    pos += '/'
                pos += p
                if m_text:
                    p_key = _norm_pos_label(p)
                    for m_item in re.split(r'[；;]', m_text):
                        m_item = m_item.strip()
                        if m_item:
                            meanings.append(m_item)
                            meanings_by_pos.setdefault(p_key, []).append(m_item)
            else:
                for m_item in re.split(r'[；;]', part):
                    m_item = m_item.strip()
                    if m_item:
                        meanings.append(m_item)

        if not pos:
            pos = 'v.'

        words.append({
            'word': word_text,
            'phonetic_us': phonetic,
            'pos': pos,
            'meanings': meanings,
            'meanings_by_pos': meanings_by_pos,
        })

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

        # 导入单词（统一走 normalize_word_data 规范化：词性/释义/按词性分组三同步）
        total = 0
        skipped = 0
        created_words = []
        for i, wd in enumerate(words, 1):
            existing = Word.objects.filter(word__iexact=wd['word']).first()
            if existing:
                if existing.unit != unit:
                    self.stdout.write(self.style.WARNING(
                        f'单词 "{wd["word"]}" 已存在于 List {existing.unit.number}，跳过'))
                else:
                    self.stdout.write(self.style.WARNING(f'跳过重复: {wd["word"]}'))
                skipped += 1
                continue

            nd = normalize_word_data(wd)
            if not nd:
                skipped += 1
                continue

            created_word = Word.objects.create(
                word=nd['word'],
                phonetic_us=nd['phonetic_us'],
                phonetic_uk=nd['phonetic_uk'],
                pos=nd['pos'],
                meanings=json.dumps(nd['meanings'], ensure_ascii=False),
                meanings_by_pos=json.dumps(nd['meanings_by_pos'], ensure_ascii=False),
                category=category,
                unit=unit,
                list_number=i,
            )
            created_words.append(created_word)
            total += 1

        # 更新单元词数
        unit.word_count = unit.words.count()
        unit.save()

        # 导入后自动 AI 补全（按词性释义 + 例句），失败不影响导入结果
        if created_words:
            try:
                ai_complete_words(created_words)
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS(
            f'\n导入完成！\n'
            f'  单元: {unit.name}\n'
            f'  导入: {total} 个单词\n'
            f'  跳过: {skipped} 个'
        ))
