"""
管理命令：从 JSON 文件导入考研词库数据
用法：python manage.py import_words data/hongbaoshu.json
"""
import json
import sys
import re
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from words.models import Unit, Word
from words.views import normalize_word_data, ai_complete_words


def clean_unit_name(name, number):
    """清理单元名称：去除 'Unit1---3' 这类合并命名中的连字符堆叠"""
    if not name:
        return f'Unit{number}'
    name = name.strip()
    # 形如 Unit1---3 / Unit8--9 / List 1-3 的合并命名，规范为起始编号
    m = re.match(r'^(Unit|List)\s*\d+\s*[-—–]+', name, re.IGNORECASE)
    if m:
        return f'Unit{number}'
    return name


class Command(BaseCommand):
    help = '从 JSON 文件导入考研词库数据'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='JSON 文件路径')
        parser.add_argument('--clear', action='store_true', help='导入前清空现有数据')

    def handle(self, *args, **options):
        json_file = options['json_file']
        clear = options['clear']

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'文件不存在: {json_file}')
        except json.JSONDecodeError as e:
            raise CommandError(f'JSON 解析错误: {e}')

        if clear:
            self.stdout.write(self.style.WARNING('清空现有单词和单元数据...'))
            Word.objects.all().delete()
            Unit.objects.all().delete()

        units_data = data.get('units', [])
        if not units_data:
            raise CommandError('JSON 数据中没有 units 字段')

        total_units = 0
        total_words = 0
        skipped = 0
        created_words = []

        for unit_data in units_data:
            unit_number = unit_data.get('number', 0)
            unit_name = clean_unit_name(unit_data.get('name', ''), unit_number)
            unit_category = unit_data.get('category', 'required')

            # 创建或更新单元
            unit, created = Unit.objects.update_or_create(
                number=unit_number,
                defaults={
                    'name': unit_name,
                    'category': unit_category,
                }
            )

            if created:
                total_units += 1

            next_list_number = (unit.words.aggregate(m=Max('list_number'))['m'] or 0) + 1

            # 导入单词
            words_list = unit_data.get('words', [])
            for word_data in words_list:
                nd = normalize_word_data(word_data)
                if not nd:
                    skipped += 1
                    continue

                existing = Word.objects.filter(word__iexact=nd['word']).first()
                if existing:
                    self.stdout.write(self.style.WARNING(f'跳过重复单词: {nd["word"]}'))
                    skipped += 1
                    continue

                created_word = Word.objects.create(
                    word=nd['word'],
                    phonetic_us=nd['phonetic_us'],
                    phonetic_uk=nd['phonetic_uk'],
                    pos=nd['pos'],
                    meanings=json.dumps(nd['meanings'], ensure_ascii=False),
                    meanings_by_pos=json.dumps(nd['meanings_by_pos'], ensure_ascii=False),
                    uncommon_meanings=json.dumps(nd['uncommon_meanings'], ensure_ascii=False),
                    collocations=json.dumps(nd['collocations'], ensure_ascii=False),
                    word_forms=json.dumps(nd['word_forms'], ensure_ascii=False),
                    example_en=nd['example_en'],
                    example_zh=nd['example_zh'],
                    category=word_data.get('category', unit_category),
                    unit=unit,
                    list_number=next_list_number,
                )
                created_words.append(created_word)
                next_list_number += 1
                total_words += 1

            # 更新单元词数
            unit.word_count = unit.words.count()
            unit.save()

            self.stdout.write(f'  List {unit_number}: {unit.words.count()} 个单词')

        # 导入后自动 AI 补全（按词性释义 + 例句），失败不影响导入结果
        if created_words:
            try:
                ai_complete_words(created_words)
            except Exception:
                pass

        self.stdout.write(self.style.SUCCESS(
            f'\n导入完成！\n'
            f'  新建单元: {total_units}\n'
            f'  导入单词: {total_words}\n'
            f'  跳过重复: {skipped}'
        ))
