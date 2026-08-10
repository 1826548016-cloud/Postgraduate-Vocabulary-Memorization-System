# -*- coding: utf-8 -*-
"""AI 按词性归类释义：python manage.py optimize_pos_meanings [--limit N] [--force] [--batch-size N] [--start N]
把每个单词的 meanings 按 pos 中的词性重新分组，写入 Word.meanings_by_pos。
用法示例：
  python manage.py optimize_pos_meanings --limit 30        # 只处理 30 个（试跑）
  python manage.py optimize_pos_meanings                   # 处理全部未处理的
  python manage.py optimize_pos_meanings --force           # 强制全部重新处理
"""
import json
import time
import urllib.request
import urllib.error

from django.core.management.base import BaseCommand

from words.models import Word
from words.ai_prompts import pos_grouping_cli_prompt
from words.views import resolve_ai_model, resolve_ai_endpoint, build_ai_headers


class Command(BaseCommand):
    help = '用 AI 把每个单词的释义按词性重新归类（写入 meanings_by_pos）'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0, help='最多处理 N 个单词（0 = 全部）')
        parser.add_argument('--force', action='store_true', help='强制重新处理已有结果的单词')
        parser.add_argument('--batch-size', type=int, default=20, help='每批单词数')
        parser.add_argument('--start', type=int, default=0, help='跳过前 N 个（断点续跑）')
        parser.add_argument('--unit', type=int, default=0, help='只处理指定单元编号的单词（0 = 全部）')

    def handle(self, *args, **opts):
        limit = opts['limit']
        force = opts['force']
        batch = max(1, opts['batch_size'])
        start = opts['start']

        qs = Word.objects.all().order_by('id')
        if opts['unit']:
            qs = qs.filter(unit__number=opts['unit'])
        if not force:
            done_ids = set(Word.objects.exclude(meanings_by_pos='')
                           .exclude(meanings_by_pos='{}').values_list('id', flat=True))
            qs = qs.exclude(id__in=done_ids)
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
                grouped = result.get(w.word)
                if isinstance(grouped, dict) and grouped:
                    w.meanings_by_pos = json.dumps(grouped, ensure_ascii=False)
                    w.save(update_fields=['meanings_by_pos'])
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
            meanings = '；'.join(w.get_meanings())
            lines.append('%s | %s | %s' % (w.word, pos, meanings))
        prompt = pos_grouping_cli_prompt(lines)
        payload = {
            'model': cfg['model_id'],
            'temperature': 0.1,
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
