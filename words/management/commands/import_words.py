"""
管理命令：从 JSON 文件导入考研词库数据
用法：python manage.py import_words data/hongbaoshu.json
"""
import json
import sys
from django.core.management.base import BaseCommand, CommandError
from words.models import Unit, Word


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

        for unit_data in units_data:
            unit_number = unit_data.get('number', 0)
            unit_name = unit_data.get('name', f'List {unit_number}')
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

            # 导入单词
            words_list = unit_data.get('words', [])
            for word_data in words_list:
                word_text = word_data.get('word', '').strip()
                if not word_text:
                    skipped += 1
                    continue

                existing = Word.objects.filter(word__iexact=word_text).first()
                if existing:
                    self.stdout.write(self.style.WARNING(f'跳过重复单词: {word_text}'))
                    skipped += 1
                    continue

                # 将 JSON 字段序列化为字符串
                meanings = word_data.get('meanings', [])
                uncommon_meanings = word_data.get('uncommon_meanings', [])
                collocations = word_data.get('collocations', [])
                word_forms = word_data.get('word_forms', {})

                Word.objects.create(
                    word=word_text,
                    phonetic_us=word_data.get('phonetic_us', ''),
                    phonetic_uk=word_data.get('phonetic_uk', ''),
                    pos=word_data.get('pos', ''),
                    meanings=json.dumps(meanings, ensure_ascii=False),
                    uncommon_meanings=json.dumps(uncommon_meanings, ensure_ascii=False),
                    collocations=json.dumps(collocations, ensure_ascii=False),
                    word_forms=json.dumps(word_forms, ensure_ascii=False),
                    example_en=word_data.get('example_en', ''),
                    example_zh=word_data.get('example_zh', ''),
                    category=word_data.get('category', unit_category),
                    unit=unit,
                    list_number=word_data.get('list_number', total_words + 1),
                )
                total_words += 1

            # 更新单元词数
            unit.word_count = unit.words.count()
            unit.save()

            self.stdout.write(f'  List {unit_number}: {unit.words.count()} 个单词')

        self.stdout.write(self.style.SUCCESS(
            f'\n导入完成！\n'
            f'  新建单元: {total_units}\n'
            f'  导入单词: {total_words}\n'
            f'  跳过重复: {skipped}'
        ))
