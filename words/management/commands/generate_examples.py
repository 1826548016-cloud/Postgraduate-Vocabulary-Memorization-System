# -*- coding: utf-8 -*-
"""AI 批量生成例句：python manage.py generate_examples [--limit N] [--force] [--batch-size N] [--start N]
为缺英文例句的单词生成中英双语例句，写入 Word.example_en / example_zh。
用法示例：
  python manage.py generate_examples --limit 30        # 只处理 30 个（试跑）
  python manage.py generate_examples                   # 处理全部缺例句的单词
  python manage.py generate_examples --force           # 强制全部重新生成
"""
import json
import time
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand

from words.models import Word
from words.views import resolve_ai_model, resolve_ai_endpoint, build_ai_headers


class Command(BaseCommand):
    help = '用 AI 为缺少例句的单词批量生成中英双语例句'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='最多处理 N 个单词（0 = 全部）')
        parser.add_argument('--force', action='store_true', help='强制重新生成已有例句的单词')
        parser.add_argument('--batch-size', type=int, default=30, help='每批单词数')
        parser.add_argument('--start', type=int, default=0, help='跳过前 N 个（断点续跑）')

    def handle(self, *args, **opts):
        limit = opts['limit']
        force = opts['force']
        batch = max(1, opts['batch_size'])
        start = opts['start']

        qs = Word.objects.all().order_by('id')
        if not force:
            qs = qs.filter(example_en='')
        if start:
            qs = qs[start:]
        if limit:
            qs = qs[:limit]
        total = qs.count()
        if total == 0:
            self.stdout.write('没有需要处理的单词')
            return

        try:
            cfg = resolve_ai_model({})
        except ValueError as e:
            self.stderr.write('AI 配置错误：%s' % e)
            return

        self.stdout.write('模型：%s，待处理 %d 个，每批 %d 个' % (cfg['model_id'], total, batch))
        words = list(qs)
        ok_count = 0
        fail = []
        for i in range(0, len(words), batch):
            chunk = words[i:i + batch]
            self.stdout.write('[%d/%d] 处理第 %d-%d 个...'
                              % (min(i + batch, total), total, i + 1, min(i + batch, total)))
            try:
                result = self._call_ai(cfg, chunk)
            except Exception as e:
                self.stderr.write('  本批失败：%s' % e)
                fail.extend(w.word for w in chunk)
                continue
            if not isinstance(result, dict):
                self.stderr.write('  返回格式异常，跳过本批')
                fail.extend(w.word for w in chunk)
                continue
            for w in chunk:
                item = result.get(w.word)
                if isinstance(item, dict) and item.get('en'):
                    w.example_en = item['en'].strip()
                    w.example_zh = (item.get('zh') or '').strip()
                    w.save(update_fields=['example_en', 'example_zh'])
                    ok_count += 1
                else:
                    fail.append(w.word)
            time.sleep(0.5)  # 避免请求过快

        self.stdout.write(self.style.SUCCESS('完成：成功 %d 个，失败 %d 个' % (ok_count, len(fail))))
        if fail:
            self.stdout.write('失败单词：%s' % ', '.join(fail[:50]))

    def _call_ai(self, cfg, chunk):
        lines = []
        for w in chunk:
            pos = w.pos or ''
            meanings = '；'.join(w.get_meanings()) or '；'.join(
                m for sub in w.get_meanings_by_pos().values() for m in sub)
            lines.append('%s | %s | %s' % (w.word, pos, meanings))
        prompt = (
            '你是英语词典编辑。下面每行是一个单词：单词 | 词性 | 释义。\n'
            '请为每个单词生成 1 个简单、地道的英文例句（尽量体现该词的常见用法），并给出对应的中文翻译。\n'
            '只输出一个严格的 JSON 对象，不要输出任何其他文字或代码块标记。\n'
            '格式：{"单词": {"en": "英文例句", "zh": "中文翻译"}, ...}\n'
            '要求：\n'
            '- 例句长度 8-20 个词，语法正确，避免生僻词，适合考研词汇学习场景\n'
            '- 中文翻译自然通顺，符合例句原意\n'
            '- 所有单词都要出现在 JSON 中，键名严格等于原单词\n\n'
            '单词列表：\n' + '\n'.join(lines)
        )
        payload = {
            'model': cfg['model_id'],
            'temperature': 0.5,
            'max_tokens': 4000,
            'messages': [{'role': 'user', 'content': prompt}],
        }
        req = urllib.request.Request(
            resolve_ai_endpoint(cfg['base_url'], cfg['endpoint']),
            data=json.dumps(payload).encode('utf-8'),
            headers=build_ai_headers(cfg['api_key']),
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        content = (result.get('choices', [{}])[0].get('message', {}).get('content', '') or '').strip()
        if not content:
            raise RuntimeError('AI 返回为空')
        # 提取 JSON（兼容 ```json ... ``` 包裹）
        s = content.find('{')
        e = content.rfind('}')
        if s == -1 or e == -1 or e <= s:
            raise RuntimeError('响应中未找到 JSON')
        return json.loads(content[s:e + 1])
