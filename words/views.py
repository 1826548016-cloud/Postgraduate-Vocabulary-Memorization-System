import json
import os
import random
import re
import shutil
import threading
import time
import urllib.request
import urllib.error
import base64
from datetime import date, timedelta, datetime
from io import BytesIO

from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q, Count, Sum, Avg, F, Max
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.db import IntegrityError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (Unit, Word, StudyProgress, StudyPlan,
                     DailyCheckIn, Favorite, Note, QuickMemory, AIModel, StudySession, UserSettings, ChatMessage, ImportLog, Conversation, LearningReport)
from .ai_prompts import (
    quick_memory_prompt, ASSISTANT_SYSTEM_PROMPT, assistant_word_context,
    pos_grouping_prompt, examples_prompt,
    RECOGNIZE_JSON_SCHEMA, RECOGNIZE_COMMON_RULES,
    recognize_image_prompt, recognize_text_prompt, recognize_file_prompt,
    ai_review_prompt, weekly_report_prompt,
)


def parse_uncommon_pos(value):
    """解析 StudyProgress.uncommon_pos 字段为 list，容错脏数据。"""
    try:
        data = json.loads(value or '[]')
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ─── 帮助函数 ───────────────────────────────────────────────

CHECKIN_DAILY_WORDS = 30  # 每日学习满 30 词自动打卡

def update_daily_checkin():
    """更新今日打卡统计数据；今日背诵满 30 词自动打卡，返回是否刚刚自动打卡"""
    today = timezone.localdate()
    checkin, _ = DailyCheckIn.objects.get_or_create(date=today)
    # 新学：learned_date 是今天
    checkin.new_words_learned = StudyProgress.objects.filter(
        learned_date=today).count()
    # 复习：今天有复习记录，且 learned_date 早于今天（不是今天第一次学的词）
    checkin.words_reviewed = StudyProgress.objects.filter(
        last_review__date=today, review_count__gt=0
    ).exclude(learned_date=today).count()
    total = checkin.today_correct + checkin.today_wrong
    if total > 0:
        checkin.correct_rate = round(checkin.today_correct / total * 100, 1)
    else:
        checkin.correct_rate = 0
    auto_checked = False
    if not checkin.is_checked and (checkin.new_words_learned + checkin.words_reviewed) >= CHECKIN_DAILY_WORDS:
        checkin.is_checked = True
        auto_checked = True
    checkin.save()
    return auto_checked

def get_streak():
    """计算连续打卡天数"""
    today = timezone.localdate()
    streak = 0
    for i in range(365):
        d = today - timedelta(days=i)
        if DailyCheckIn.objects.filter(date=d, is_checked=True).exists():
            streak += 1
        else:
            break
    return streak

# ─── 页面视图 ───────────────────────────────────────────────

def dashboard(request):
    today = timezone.localdate()
    settings_obj = UserSettings.get_settings()
    active_plan = StudyPlan.objects.filter(is_active=True).first()

    today_new = StudyProgress.objects.filter(
        learned_date=today).count()
    today_review = StudyProgress.objects.filter(
        last_review__date=today, review_count__gt=0
    ).exclude(learned_date=today).count()
    # 复习目标：所有已学词汇（status不为new）
    review_due = StudyProgress.objects.exclude(status='new').count()

    total_words = Word.objects.count()
    mastered_words = StudyProgress.objects.filter(status='mastered').count()
    # also count learning+reviewing
    learning_words = StudyProgress.objects.exclude(status='new').exclude(status='mastered').count()

    # by category
    cats = [('required', '必考词'), ('basic', '基础词'), ('advanced', '超纲词')]
    category_stats = {}
    for code, label in cats:
        total = Word.objects.filter(category=code).count()
        mastered = StudyProgress.objects.filter(word__category=code, status='mastered').count()
        category_stats[code] = {'label': label, 'total': total, 'mastered': mastered}

    streak = get_streak()
    today_checkin = DailyCheckIn.objects.filter(date=today).first()
    today_duration = today_checkin.study_duration if today_checkin else 0

    checkin_words = today_new + today_review
    checkin_threshold = CHECKIN_DAILY_WORDS
    checkin_percent = min(100, round(checkin_words / checkin_threshold * 100)) if checkin_threshold else 0

    # 刷题打卡热力图：近一年每日做题量（新学 + 复习），实时统计保证数据完整
    heat_start = today - timedelta(days=364)
    heat_new = StudyProgress.objects.filter(
        learned_date__gte=heat_start
    ).values('learned_date').annotate(cnt=Count('id'))
    heat_review = StudyProgress.objects.filter(
        last_review__date__gte=heat_start, review_count__gt=0
    ).exclude(learned_date__gte=F('last_review__date')) \
     .values('last_review__date').annotate(cnt=Count('id'))
    heat_map = {}
    for x in heat_new:
        heat_map[x['learned_date']] = heat_map.get(x['learned_date'], 0) + x['cnt']
    for x in heat_review:
        d = x['last_review__date']
        heat_map[d] = heat_map.get(d, 0) + x['cnt']
    heatmap_days = {}
    d = heat_start
    while d <= today:
        heatmap_days[d.isoformat()] = heat_map.get(d, 0)
        d += timedelta(days=1)
    total_study_days = sum(1 for v in heat_map.values() if v > 0)

    # 计划驱动的今日学习数据
    plan_today = None
    if active_plan:
        plan_today = _get_plan_today_data(active_plan, today)

    context = {
        'today_new': today_new,
        'today_review': today_review,
        'review_due': review_due,
        'settings': settings_obj,
        'plan': active_plan,
        'plan_today': plan_today,
        'total_words': total_words,
        'mastered_words': mastered_words,
        'learning_words': learning_words,
        'category_stats': category_stats,
        'streak': streak,
        'today_checkin': today_checkin,
        'checkin_words': checkin_words,
        'checkin_threshold': checkin_threshold,
        'checkin_percent': checkin_percent,
        'heatmap_days': heatmap_days,
        'total_study_days': total_study_days,
        'today_duration': today_duration,
    }
    return render(request, 'dashboard.html', context)


def word_list(request):
    units = Unit.objects.annotate(
        mastered=Count('words__progress', filter=Q(words__progress__status='mastered'))
    ).all()
    return render(request, 'word_list.html', {'units': units})


def ai_import(request):
    """AI 单词导入独立页面"""
    units = Unit.objects.annotate(
        mastered=Count('words__progress', filter=Q(words__progress__status='mastered'))
    ).all()
    return render(request, 'ai_import.html', {'units': units})


def word_detail(request, word_id):
    word = get_object_or_404(Word, id=word_id)
    progress, _ = StudyProgress.objects.get_or_create(word=word)
    is_fav = hasattr(word, 'favorite')
    note = getattr(word, 'note', None)
    return render(request, 'word_detail.html', {
        'word': word,
        'progress': progress,
        'is_favorite': is_fav,
        'note': note,
    })


def learn_start(request):
    units = Unit.objects.all()
    today = timezone.localdate()
    plan_today = None
    active_plan = StudyPlan.objects.filter(is_active=True).first()
    if active_plan:
        plan_today = _get_plan_today_data(active_plan, today)
    return render(request, 'learn_start.html', {'units': units, 'plan_today': plan_today})


def learn_session(request):
    mode = request.GET.get('mode', 'sequential')
    check = request.GET.get('check', 'none')
    unit_ids = request.GET.getlist('units')
    scope = request.GET.get('scope', 'unknown')

    query = Word.objects.all()
    if unit_ids:
        query = query.filter(unit__number__in=unit_ids)

    # 永不忘记的词（is_excluded）不再出现
    query = query.exclude(progress__is_excluded=True)

    if scope == 'mastered':
        # 会的词：已掌握
        query = query.filter(progress__status='mastered')
    else:
        # 不会的词：未掌握（默认）
        query = query.exclude(progress__status='mastered')

    words = list(query)

    if mode in ('random', 'cover_en', 'cover_zh'):
        random.shuffle(words)
    else:
        words = sorted(words, key=lambda w: (w.unit.number, w.list_number))

    # 批量预取进度，避免 N+1
    word_ids = [w.id for w in words]
    progress_map = {
        p.word_id: p for p in StudyProgress.objects.filter(word_id__in=word_ids)
    }

    word_data = []
    for w in words:
        p = progress_map.get(w.id)
        word_data.append({
            'id': w.id,
            'word': w.word,
            'phonetic_us': w.phonetic_us,
            'pos': w.pos,
            'meanings': w.get_meanings(),
            'meanings_by_pos': w.get_meanings_by_pos(),
            'example_en': w.example_en,
            'example_zh': w.example_zh,
            'unit_number': w.unit.number if w.unit else None,
            'uncommon_pos': parse_uncommon_pos(p.uncommon_pos if p else None),
        })

    # 用 session 记录词 ID 列表（供复习页用）
    request.session['learn_words'] = [w['id'] for w in word_data]
    request.session['learn_mode'] = mode

    return render(request, 'learn_session.html', {
        'word_count': len(word_data),
        'mode': mode,
        'check': check,
        'words_json': json.dumps(word_data, ensure_ascii=False),
    })


def review_start(request):
    """复习：选择单元与范围（与背诵入口一致）"""
    units = Unit.objects.annotate(
        mastered=Count('words__progress', filter=Q(words__progress__status='mastered'))
    ).all()
    return render(request, 'review_start.html', {'units': units})


def review_session(request):
    """复习：从选定范围（单元/掌握状态）的已学词汇中随机抽取。
    - mode=random 开始新一轮随机复习（清空已复习记录）
    - random=1 继续上一轮随机复习（跳过已复习过的词）
    - count=N 指定本轮抽取数量（默认使用每日复习目标）
    """
    today = timezone.localdate()
    settings_obj = UserSettings.get_settings()

    # 范围参数：units 多选单元编号；scope 掌握状态
    unit_ids = request.GET.getlist('units')
    scope = request.GET.get('scope', 'all')

    # 随机复习模式
    random_mode = request.GET.get('mode') == 'random' or request.GET.get('random') == '1'
    if request.GET.get('mode') == 'random':
        # 新一轮随机复习：清空历史记录
        request.session['random_review_done'] = []

    # 本轮抽取数量
    target = max(1, settings_obj.daily_review_target)
    if request.GET.get('count'):
        try:
            target = max(1, min(int(request.GET.get('count')), 500))
        except (TypeError, ValueError):
            pass

    query = StudyProgress.objects.exclude(status='new').select_related('word')
    # 永不忘记的词（is_excluded）不再出现
    query = query.exclude(is_excluded=True)
    if unit_ids:
        query = query.filter(word__unit__number__in=unit_ids)
    if scope == 'unmastered':
        query = query.exclude(status='mastered')
    elif scope == 'mastered':
        query = query.filter(status='mastered')

    all_progress = list(query)

    # 随机复习：跳过已复习过的词（session 记录）
    done_ids = request.session.get('random_review_done', []) or []
    if random_mode and done_ids:
        done_set = set(done_ids)
        all_progress = [p for p in all_progress if p.id not in done_set]

    random.shuffle(all_progress)
    batch = all_progress[:target]

    # 记录本轮已复习的词（随机模式）
    if random_mode and batch:
        done_ids = request.session.get('random_review_done', []) or []
        done_ids.extend(p.id for p in batch)
        request.session['random_review_done'] = done_ids[-2000:]

    word_data = []
    for p in batch:
        w = p.word
        word_data.append({
            'id': w.id,
            'word': w.word,
            'phonetic_us': w.phonetic_us,
            'pos': w.pos,
            'meanings': w.get_meanings(),
            'meanings_by_pos': w.get_meanings_by_pos(),
            'example_en': w.example_en,
            'example_zh': w.example_zh,
            'error_count': p.error_count,
            'review_count': p.review_count,
            'status': p.status,
            'uncommon_pos': parse_uncommon_pos(p.uncommon_pos),
        })

    mastered_count = len([p for p in batch if p.status == 'mastered'])
    unmastered_count = len(batch) - mastered_count

    # 范围描述（复习页顶部提示用）
    scope_label = {
        'all': '全部已学词',
        'unmastered': '未掌握词',
        'mastered': '已掌握词',
    }.get(scope, '全部已学词')
    if unit_ids:
        unit_names = Unit.objects.filter(number__in=unit_ids).values_list('number', flat=True)
        unit_label = '、'.join('Unit %s' % n for n in sorted(unit_names))
    else:
        unit_label = '全部单元'

    # 继续随机复习链接参数
    units_param = '&'.join('units=%s' % u for u in unit_ids)

    return render(request, 'review_session.html', {
        'review_count': len(word_data),
        'words_json': json.dumps(word_data, ensure_ascii=False),
        'total_due': len(all_progress),  # 范围内可抽取的已学词总数
        'remaining_due': max(0, len(all_progress) - len(batch)),
        'daily_review_target': settings_obj.daily_review_target,
        'batch_date': today.isoformat(),
        'unmastered_in_batch': unmastered_count,
        'mastered_in_batch': mastered_count,
        'scope_label': scope_label,
        'unit_label': unit_label,
        'random_mode': random_mode,
        'random_count': target,
        'scope': scope,
        'units_param': units_param,
    })


def statistics(request):
    return render(request, 'stats.html')


def exam(request):
    """模拟考试：配置页"""
    units = Unit.objects.all()
    return render(request, 'exam.html', {'units': units})


def study_plan(request):
    plans = StudyPlan.objects.all().order_by('-is_active', '-created_at')
    today = timezone.localdate()
    # 为激活计划计算今日学习数据
    plan_today = None
    active_plan = StudyPlan.objects.filter(is_active=True).first()
    if active_plan:
        plan_today = _get_plan_today_data(active_plan, today)
    return render(request, 'plan.html', {'plans': plans, 'plan_today': plan_today})


def plan_create(request):
    """创建/编辑学习计划的独立页面"""
    units = Unit.objects.all()
    plan = None
    plan_id = request.GET.get('plan_id')
    if plan_id:
        plan = get_object_or_404(StudyPlan, id=plan_id)
    return render(request, 'plan_form.html', {'units': units, 'plan': plan})


def settings_page(request):
    settings_obj = UserSettings.get_settings()
    ai_models = AIModel.objects.all().order_by('-enabled', 'id')
    return render(request, 'settings.html', {'settings': settings_obj, 'ai_models': ai_models})


def favorites_list(request):
    favs = Favorite.objects.select_related('word__unit').all()
    return render(request, 'favorites.html', {'favorites': favs})


def weak_words(request):
    """薄弱词：从全部薄弱词中精选最需要巩固的 50 个。
    选词机制（薄弱指数综合评分）：
      - 错误次数 ×3（核心信号）
      - 未掌握 +2（学习中 / 复习中）
      - 掌握等级越低加分越多（(5-等级)×0.4）
      - 反复复习仍出错加分（复习次数 ×0.2，封顶 20 次）
      - 近期仍在复习的优先（7 天内 +1.5，30 天内 +0.8）
    按指数从高到低取前 50 个；顶部统计仍展示全部薄弱词总览。
    """
    progress_qs = (
        StudyProgress.objects
        .filter(Q(error_count__gt=0) | Q(status__in=['learning', 'reviewing']))
        .select_related('word__unit')
    )
    now = timezone.now()

    pool = []
    total_errors = 0
    reviewed = 0
    for p in progress_qs:
        total_errors += p.error_count
        if p.review_count > 0:
            reviewed += 1
        score = p.error_count * 3.0
        if p.status != 'mastered':
            score += 2.0
        score += max(0, 5 - p.mastery_level) * 0.4
        score += min(p.review_count, 20) * 0.2
        if p.last_review:
            days_since = (now - p.last_review).days
            if days_since <= 7:
                score += 1.5
            elif days_since <= 30:
                score += 0.8
        pool.append((score, p))

    pool.sort(key=lambda x: (-x[0], -x[1].error_count, -x[1].review_count))
    selected = pool[:50]

    items = []
    for score, p in selected:
        w = p.word
        items.append({
            'id': w.id,
            'word': w.word,
            'phonetic_us': w.phonetic_us,
            'phonetic_uk': w.phonetic_uk,
            'pos': w.pos,
            'meanings': w.get_meanings(),
            'meanings_by_pos': w.get_meanings_by_pos(),
            'status': p.status,
            'status_label': p.get_status_display(),
            'mastery_level': p.mastery_level,
            'error_count': p.error_count,
            'review_count': p.review_count,
            'unit_number': w.unit.number,
            'unit_name': w.unit.name,
            'is_favorite': hasattr(w, 'favorite'),
            'score': round(score, 1),
        })

    stats = {
        'total': len(pool),
        'unmastered': sum(1 for _, p in pool if p.status != 'mastered'),
        'total_errors': total_errors,
        'reviewed': reviewed,
    }
    return render(request, 'weak_words.html', {
        'items': items,
        'stats': stats,
        'selected_count': len(items),
        'pool_count': len(pool),
    })


def focus_mode(request):
    units = Unit.objects.annotate(
        mastered=Count('words__progress', filter=Q(words__progress__status='mastered'))
    ).all()
    return render(request, 'focus.html', {'units': units})


# ─── API 视图 ───────────────────────────────────────────────

def api_words(request):
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    unit = request.GET.get('unit', '')
    status = request.GET.get('status', '')
    sort = request.GET.get('sort', '')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 50))

    qs = Word.objects.select_related('unit', 'progress').all()
    if search:
        qs = qs.filter(Q(word__icontains=search) | Q(meanings__icontains=search))
    if category:
        qs = qs.filter(category=category)
    if unit:
        qs = qs.filter(unit__number=int(unit))
    if status:
        if status == 'unknown':
            qs = qs.filter(
                Q(progress__isnull=True) |
                Q(progress__status__in=['new', 'learning', 'reviewing'])
            )
        elif status == 'excluded':
            qs = qs.filter(progress__is_excluded=True)
        else:
            qs = qs.filter(progress__status=status)

    # 排序：alpha=按单词字母序，空=默认(单元+序号)
    if sort == 'alpha':
        qs = qs.order_by('word')
    elif sort == 'alpha_desc':
        qs = qs.order_by('-word')

    total = qs.count()
    start = (page - 1) * per_page
    words_qs = qs[start:start + per_page]

    words_data = []
    for w in words_qs:
        has_fav = hasattr(w, 'favorite')
        p = getattr(w, 'progress', None)
        words_data.append({
            'id': w.id,
            'word': w.word,
            'phonetic_us': w.phonetic_us,
            'phonetic_uk': w.phonetic_uk,
            'pos': w.pos,
            'meanings': w.get_meanings(),
            'meanings_by_pos': w.get_meanings_by_pos(),
            'uncommon_meanings': w.get_uncommon_meanings(),
            'collocations': w.get_collocations(),
            'example_en': w.example_en,
            'example_zh': w.example_zh,
            'category': w.category,
            'unit_number': w.unit.number,
            'unit_name': w.unit.name,
            'status': p.status if p else 'new',
            'mastery_level': p.mastery_level if p else 0,
            'is_excluded': p.is_excluded if p else False,
            'is_favorite': has_fav,
        })

    total_excluded = Word.objects.filter(progress__is_excluded=True).count()

    return JsonResponse({
        'words': words_data,
        'total': total,
        'page': page,
        'total_excluded': total_excluded,
    })


def api_word_detail(request, word_id):
    word = get_object_or_404(Word.objects.select_related('unit', 'progress'), id=word_id)
    progress, _ = StudyProgress.objects.get_or_create(word=word)
    is_fav = hasattr(word, 'favorite')
    note_obj = getattr(word, 'note', None)

    data = {
        'id': word.id,
        'word': word.word,
        'phonetic_us': word.phonetic_us,
        'phonetic_uk': word.phonetic_uk,
        'pos': word.pos,
        'meanings': word.get_meanings(),
        'meanings_by_pos': word.get_meanings_by_pos(),
        'uncommon_meanings': word.get_uncommon_meanings(),
        'collocations': word.get_collocations(),
        'word_forms': word.get_word_forms(),
        'example_en': word.example_en,
        'example_zh': word.example_zh,
        'category': word.category,
        'unit_number': word.unit.number,
        'unit_name': word.unit.name,
        'list_number': word.list_number,
        'progress': {
            'status': progress.status,
            'mastery_level': progress.mastery_level,
            'review_count': progress.review_count,
            'error_count': progress.error_count,
            'last_review': progress.last_review,
            'next_review': progress.next_review,
        },
        'is_favorite': is_fav,
        'note': {'content': note_obj.content, 'page_number': note_obj.page_number} if note_obj else None,
    }
    return JsonResponse(data)


@csrf_exempt
@require_http_methods(['POST'])
def api_mark_word(request, action, word_id):
    try:
        word = get_object_or_404(Word, id=word_id)
        progress, created = StudyProgress.objects.get_or_create(word=word)
        today = timezone.localdate()
        now = timezone.now()

        if created or progress.status == 'new':
            progress.learned_date = today
            progress.is_today_new = True

        if action == 'mastered':
            progress.mastery_level = 5
            progress.status = 'mastered'
        elif action in ('fuzzy', 'unknown'):
            progress.mastery_level = 0
            progress.status = 'learning'
            progress.error_count += 1
        else:
            return JsonResponse({'error': '无效操作'}, status=400)

        progress.review_count += 1
        progress.last_review = now
        progress.save()

        # 更新今日正确率统计
        checkin, _ = DailyCheckIn.objects.get_or_create(date=today)
        if action == 'mastered':
            checkin.today_correct += 1
        else:
            checkin.today_wrong += 1
        checkin.save()

        auto_checked = update_daily_checkin()

        return JsonResponse({
            'success': True,
            'status': progress.status,
            'mastery_level': progress.mastery_level,
            'auto_checked': auto_checked,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def api_mark_skip(request, word_id):
    """标记单词为「永不忘记」：之后不再出现在背诵/复习中。"""
    try:
        word = get_object_or_404(Word, id=word_id)
        progress, _ = StudyProgress.objects.get_or_create(word=word)
        progress.is_excluded = True
        if progress.status == 'new':
            progress.status = 'mastered'  # 视为已掌握，保证统计口径一致
        progress.save()
        return JsonResponse({
            'success': True,
            'is_excluded': True,
            'status': progress.status,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def api_mark_unskip(request, word_id):
    """取消「永不忘记」标记：恢复出现在背诵/复习中。"""
    try:
        word = get_object_or_404(Word, id=word_id)
        progress = StudyProgress.objects.filter(word=word).first()
        if not progress:
            return JsonResponse({'success': True, 'is_excluded': False})
        progress.is_excluded = False
        progress.save()
        return JsonResponse({
            'success': True,
            'is_excluded': False,
            'status': progress.status,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


MEANING_JUDGE_PROMPT = '''你是考研英语词汇老师，负责判定学生默写的单词中文释义是否合格。

单词：{word}
标准释义：{meanings}

学生的答案：{answer}

请判定学生答案是否表达了该单词的核心含义：
1. 只要学生答案大致表达了核心含义（同义词、近义表达、简洁概括、个别用词不准均可），就算「correct」，本模式要求宽松，大致对即可判对。
2. 只有沾边但完全没写到点子上、或明显答非所问的，才算「partial」或「wrong」。
3. 完全不对、明显错误、或与单词无关的，算「wrong」。

只输出 JSON，不要输出其他内容，格式：
{{"verdict": "correct 或 partial 或 wrong", "comment": "一句话中文点评，指出对在哪或错在哪，并给出参考释义"}}
'''


def _normalize_spelling(text):
    """拼写判定归一化：小写、去首尾空格、去掉非字母数字字符（容错连字符/撇号/空格）"""
    return re.sub(r'[^a-z0-9]', '', (text or '').lower().strip())


def _judge_meaning_answer(word, answer, data):
    """判定释义默写答案：AI 优先（跟随设置里选的模型），失败退回本地比对。
    返回 (verdict, comment, used_ai)。"""
    if not (answer or '').strip():
        return 'wrong', '未作答', False

    meanings = word.get_meanings()
    by_pos = word.get_meanings_by_pos()
    meaning_parts = list(meanings)
    for pos, ms in by_pos.items():
        if ms:
            meaning_parts.append('%s：%s' % (pos, '；'.join(ms)))
    meaning_text = '；'.join(meaning_parts)

    verdict = 'wrong'
    comment = ''
    used_ai = False
    settings_obj = UserSettings.get_settings()

    if settings_obj.meaning_check_model and not data.get('model_id'):
        data['model_id'] = settings_obj.meaning_check_model_id

    if settings_obj.use_ai_meaning_check and answer:
        try:
            cfg = resolve_ai_model(data)
            prompt = MEANING_JUDGE_PROMPT.format(
                word=word.word, meanings=meaning_text, answer=answer)
            content = _ai_chat_once(cfg, prompt, max_tokens=500)
            parsed = _extract_json_object(content)
            v = parsed.get('verdict')
            if v in ('correct', 'partial', 'wrong'):
                verdict = v
            comment = (parsed.get('comment') or '').strip()
            used_ai = True
        except Exception:
            used_ai = False

    if not used_ai:
        # 本地比对兜底：去掉标点空白后看答案与任一标准释义是否互相包含
        norm_answer = re.sub(r'[\s，。、；：,.!?；、]', '', answer)
        hit = False
        for m in meaning_parts:
            norm_m = re.sub(r'[\s，。、；：,.!?；、]', '', m)
            if not norm_m:
                continue
            if norm_m in norm_answer or norm_answer in norm_m:
                hit = True
                break
        verdict = 'correct' if hit else 'wrong'
        comment = '本地判定：%s' % ('与标准释义一致' if hit else '与标准释义不符')

    return verdict, comment, used_ai


@csrf_exempt
@require_http_methods(['POST'])
def api_spelling_check(request, word_id):
    """拼写检测：看中文默写英文，本地判定是否与标准拼写一致"""
    try:
        data = json.loads(request.body)
        answer = (data.get('answer') or '').strip()
        word = get_object_or_404(Word, id=word_id)
        progress, created = StudyProgress.objects.get_or_create(word=word)
        today = timezone.localdate()
        now = timezone.now()

        if created or progress.status == 'new':
            progress.learned_date = today
            progress.is_today_new = True

        correct = bool(answer) and _normalize_spelling(answer) == _normalize_spelling(word.word)

        progress.spelling_attempts += 1
        if correct:
            progress.spelling_correct += 1
            progress.mastery_level = 5
            progress.status = 'mastered'
        else:
            progress.error_count += 1
            progress.mastery_level = 0
            progress.status = 'learning'
        progress.review_count += 1
        progress.last_review = now
        progress.save()

        checkin, _ = DailyCheckIn.objects.get_or_create(date=today)
        if correct:
            checkin.today_correct += 1
        else:
            checkin.today_wrong += 1
        checkin.save()

        auto_checked = update_daily_checkin()

        return JsonResponse({
            'success': True,
            'correct': correct,
            'status': progress.status,
            'auto_checked': auto_checked,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_meaning_check(request, word_id):
    """释义默写：看英文写中文意思，AI 判定正确 / 部分正确 / 错误（失败时退回本地比对）"""
    try:
        data = json.loads(request.body)
        answer = (data.get('answer') or '').strip()
        word = get_object_or_404(Word, id=word_id)
        progress, created = StudyProgress.objects.get_or_create(word=word)

        verdict, comment, used_ai = _judge_meaning_answer(word, answer, data)

        today = timezone.localdate()
        now = timezone.now()
        if created or progress.status == 'new':
            progress.learned_date = today
            progress.is_today_new = True

        progress.meaning_attempts += 1
        if verdict in ('correct', 'partial'):
            progress.meaning_correct += 1
            progress.mastery_level = 5
            progress.status = 'mastered'
        else:
            progress.error_count += 1
            progress.mastery_level = 0
            progress.status = 'learning'
        progress.review_count += 1
        progress.last_review = now
        progress.save()

        checkin, _ = DailyCheckIn.objects.get_or_create(date=today)
        if verdict in ('correct', 'partial'):
            checkin.today_correct += 1
        else:
            checkin.today_wrong += 1
        checkin.save()

        auto_checked = update_daily_checkin()

        return JsonResponse({
            'success': True,
            'verdict': verdict,
            'comment': comment,
            'used_ai': used_ai,
            'status': progress.status,
            'auto_checked': auto_checked,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_toggle_mastery(request, word_id):
    """在 会(mastered) 与 不会(未掌握) 之间切换"""
    try:
        word = get_object_or_404(Word, id=word_id)
        progress, _ = StudyProgress.objects.get_or_create(word=word)
        today = timezone.localdate()

        checkin, _ = DailyCheckIn.objects.get_or_create(date=today)
        if progress.status == 'mastered':
            # → 不会
            progress.status = 'learning'
            progress.mastery_level = 0
            progress.save()
            checkin.today_wrong += 1
            checkin.save()
            auto_checked = update_daily_checkin()
            return JsonResponse({
                'success': True,
                'is_mastered': False,
                'status_label': '不会',
                'auto_checked': auto_checked,
            })
        else:
            # → 会
            progress.status = 'mastered'
            progress.mastery_level = 5
            progress.review_count += 1
            progress.last_review = timezone.now()
            if progress.learned_date is None:
                progress.learned_date = today
            progress.save()
            checkin.today_correct += 1
            checkin.save()
            auto_checked = update_daily_checkin()
            return JsonResponse({
                'success': True,
                'is_mastered': True,
                'status_label': '会',
                'auto_checked': auto_checked,
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_mark_uncommon_pos(request, word_id):
    """标记/取消标记某个词性为陌生（add/remove）。"""
    try:
        data = json.loads(request.body or '{}')
        pos = str(data.get('pos', '')).strip()
        action = data.get('action', 'add')
        if not pos:
            return JsonResponse({'error': '缺少词性'}, status=400)
        if action not in ('add', 'remove'):
            return JsonResponse({'error': 'action 参数无效'}, status=400)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'error': '参数格式错误'}, status=400)

    # 处理并发 get_or_create 的竞争条件
    try:
        progress, _ = StudyProgress.objects.get_or_create(word_id=word_id)
    except IntegrityError:
        progress = StudyProgress.objects.get(word_id=word_id)

    uncommon = parse_uncommon_pos(progress.uncommon_pos)

    if action == 'add' and pos not in uncommon:
        uncommon.append(pos)
    elif action == 'remove' and pos in uncommon:
        uncommon = [p for p in uncommon if p != pos]

    progress.uncommon_pos = json.dumps(uncommon, ensure_ascii=False)
    progress.save(update_fields=['uncommon_pos'])
    return JsonResponse({'success': True, 'uncommon_pos': uncommon})


def api_today(request):
    today = timezone.localdate()
    settings_obj = UserSettings.get_settings()

    # 今日新词 - 如果没有设置今日新词，从新词中取 daily_new_target 个
    new_words = Word.objects.filter(progress__isnull=True)[:settings_obj.daily_new_target]
    new_list = [{
        'id': w.id,
        'word': w.word,
        'phonetic_us': w.phonetic_us,
        'pos': w.pos,
        'meanings': w.get_meanings(),
        'meanings_by_pos': w.get_meanings_by_pos(),
    } for w in new_words]

    # 今日需复习：从所有已学词中随机抽取（排除永不忘记的词）
    all_progress = list(StudyProgress.objects.exclude(status='new')
                        .exclude(is_excluded=True).select_related('word'))
    random.shuffle(all_progress)
    review_batch = all_progress[:settings_obj.daily_review_target]

    review_list = [{
        'id': p.word.id,
        'word': p.word.word,
        'phonetic_us': p.word.phonetic_us,
        'pos': p.word.pos,
        'meanings': p.word.get_meanings(),
        'meanings_by_pos': p.word.get_meanings_by_pos(),
        'mastery_level': p.mastery_level,
        'uncommon_pos': parse_uncommon_pos(p.uncommon_pos),
    } for p in review_batch]

    due_count = len(all_progress)  # 总已学词数即为待复习数

    return JsonResponse({
        'new_words': new_list,
        'review_words': review_list,
        'new_count': len(new_list),
        'review_count': len(review_list),
        'due_count': due_count,
        'daily_new_target': settings_obj.daily_new_target,
        'daily_review_target': settings_obj.daily_review_target,
    })


@csrf_exempt
@require_http_methods(['POST'])
def api_reset_progress(request):
    try:
        data = json.loads(request.body)
        scope = data.get('scope', 'all')
        if scope == 'all':
            StudyProgress.objects.all().delete()
            DailyCheckIn.objects.all().delete()
            message = '已清空全部学习进度'
        elif scope == 'unit':
            unit_number = data.get('unit_number')
            Word.objects.filter(unit__number=unit_number).update(
                progress=None)
            StudyProgress.objects.filter(word__unit__number=unit_number).delete()
            message = f'已清空 List {unit_number} 的学习进度'
        else:
            return JsonResponse({'error': '无效 scope'}, status=400)

        return JsonResponse({'success': True, 'message': message})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_plan_create(request):
    try:
        data = json.loads(request.body)
        # 停用其他计划
        StudyPlan.objects.filter(is_active=True).update(is_active=False)
        plan = StudyPlan.objects.create(
            name=data.get('name', '我的学习计划'),
            daily_new_words=int(data.get('daily_new_words', 30)),
            daily_review_count=int(data.get('daily_review_count', 50)),
            target_date=datetime.strptime(data['target_date'], '%Y-%m-%d').date() if data.get('target_date') else None,
            unit_range=json.dumps(data.get('unit_range', [])),
            is_active=True,
        )
        return JsonResponse({'success': True, 'plan_id': plan.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_plan_update(request, plan_id):
    try:
        data = json.loads(request.body)
        plan = get_object_or_404(StudyPlan, id=plan_id)
        if 'name' in data:
            plan.name = data['name']
        if 'daily_new_words' in data:
            plan.daily_new_words = int(data['daily_new_words'])
        if 'daily_review_count' in data:
            plan.daily_review_count = int(data['daily_review_count'])
        if 'target_date' in data and data['target_date']:
            plan.target_date = datetime.strptime(data['target_date'], '%Y-%m-%d').date()
        if 'unit_range' in data:
            plan.unit_range = json.dumps(data['unit_range'])
        if 'is_active' in data:
            if data['is_active']:
                StudyPlan.objects.filter(is_active=True).exclude(id=plan.id).update(is_active=False)
            plan.is_active = data['is_active']
        plan.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def api_plan_delete(request, plan_id):
    """删除学习计划"""
    try:
        plan = get_object_or_404(StudyPlan, id=plan_id)
        plan_name = plan.name
        plan.delete()
        return JsonResponse({
            'success': True,
            'message': f'已删除计划 "{plan_name}"',
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def _get_plan_today_data(plan, today):
    """计算激活计划的今日学习数据（供页面渲染和 API 共用）"""
    unit_nums = plan.get_unit_range()

    # 计划范围内的总词数 / 已掌握词数
    if unit_nums:
        total_words = Word.objects.filter(unit__number__in=unit_nums).count()
        mastered = StudyProgress.objects.filter(
            word__unit__number__in=unit_nums, status='mastered').count()
    else:
        total_words = Word.objects.count()
        mastered = StudyProgress.objects.filter(status='mastered').count()

    # 今日已学新词数
    today_new_done = StudyProgress.objects.filter(
        learned_date=today,
        **({'word__unit__number__in': unit_nums} if unit_nums else {})
    ).count()

    # 今日已复习数
    today_review_done = StudyProgress.objects.filter(
        last_review__date=today, review_count__gt=0,
        **({'word__unit__number__in': unit_nums} if unit_nums else {})
    ).exclude(learned_date=today).count()

    # 剩余单词
    remaining = max(0, total_words - mastered)

    # 预计天数
    est_days = (remaining + plan.daily_new_words - 1) // plan.daily_new_words if plan.daily_new_words > 0 else 0

    # 倒计时
    days_left = (plan.target_date - today).days if plan.target_date else None

    # 整体进度百分比
    overall_pct = round(mastered / total_words * 100, 1) if total_words > 0 else 0

    # 本周每日完成情况（周一到周日）
    weekday = today.weekday()  # 0=周一
    week_start = today - timedelta(days=weekday)
    weekly = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        new_cnt = StudyProgress.objects.filter(
            learned_date=d,
            **({'word__unit__number__in': unit_nums} if unit_nums else {})
        ).count()
        rev_cnt = StudyProgress.objects.filter(
            last_review__date=d, review_count__gt=0,
            **({'word__unit__number__in': unit_nums} if unit_nums else {})
        ).exclude(learned_date=d).count()
        total_cnt = new_cnt + rev_cnt
        if d > today:
            status = 'future'
        elif total_cnt == 0:
            status = 'missed'
        elif d == today:
            status = 'today'
        else:
            status = 'done'
        weekly.append({
            'date': d.isoformat(),
            'weekday': ['一', '二', '三', '四', '五', '六', '日'][i],
            'new_count': new_cnt,
            'review_count': rev_cnt,
            'total': total_cnt,
            'status': status,
        })

    return {
        'plan_id': plan.id,
        'plan_name': plan.name,
        'daily_new_target': plan.daily_new_words,
        'daily_review_target': plan.daily_review_count,
        'today_new_done': today_new_done,
        'today_review_done': today_review_done,
        'total_words': total_words,
        'mastered': mastered,
        'remaining': remaining,
        'estimated_days': est_days,
        'days_left': days_left,
        'overall_percent': overall_pct,
        'target_date': plan.target_date.isoformat() if plan.target_date else None,
        'weekly': weekly,
    }


@csrf_exempt
@require_http_methods(['GET'])
def api_plan_today(request):
    """返回当前激活计划的今日学习任务与进度"""
    plan = StudyPlan.objects.filter(is_active=True).first()
    if not plan:
        return JsonResponse({'success': False, 'error': '没有激活的学习计划'}, status=404)
    today = timezone.localdate()
    data = _get_plan_today_data(plan, today)
    data['success'] = True
    return JsonResponse(data)


def api_stats(request, period):
    today = timezone.localdate()
    if period == '7':
        start_date = today - timedelta(days=7)
    elif period == '30':
        start_date = today - timedelta(days=30)
    else:
        start_date = today - timedelta(days=365)

    checkins = DailyCheckIn.objects.filter(
        date__gte=start_date, date__lte=today
    )
    checkin_map = {c.date: c for c in checkins}

    # 每日新学/复习数据按进度实时统计（不依赖打卡快照），保证近几天数据完整
    # 新学：learned_date 在范围内的所有词
    new_by_day = StudyProgress.objects.filter(
        learned_date__gte=start_date
    ).values('learned_date').annotate(cnt=Count('id'))
    new_map = {x['learned_date']: x['cnt'] for x in new_by_day}

    # 复习：last_review 在范围内，且 learned_date 早于该日期（排除当天新学的词）
    review_by_day = StudyProgress.objects.filter(
        last_review__date__gte=start_date, review_count__gt=0
    ).exclude(learned_date__gte=F('last_review__date')) \
     .values('last_review__date').annotate(cnt=Count('id'))
    review_map = {x['last_review__date']: x['cnt'] for x in review_by_day}

    # 连续日期序列：无学习记录的日期补 0，保证趋势图覆盖整个周期（含今天）
    days_data = []
    d = start_date
    while d <= today:
        c = checkin_map.get(d)
        days_data.append({
            'date': d.isoformat(),
            'new_words': new_map.get(d, 0),
            'reviewed': review_map.get(d, 0),
            'duration': c.study_duration if c else 0,
            'correct_rate': c.correct_rate if c else 0,
        })
        d += timedelta(days=1)

    summary = checkins.aggregate(
        avg_correct=Avg('correct_rate'),
        total_duration=Sum('study_duration'),
    )
    summary['total_new'] = sum(x['new_words'] for x in days_data)
    summary['total_reviewed'] = sum(x['reviewed'] for x in days_data)

    # 易错词
    error_words = StudyProgress.objects.select_related('word').filter(
        error_count__gt=0
    ).order_by('-error_count')[:20]

    error_list = [{
        'word': e.word.word,
        'error_count': e.error_count,
        'review_count': e.review_count,
        'status': e.status,
    } for e in error_words]

    # 分类进度
    cats = [('required', '必考词'), ('basic', '基础词'), ('advanced', '超纲词')]
    cat_progress = {}
    for code, label in cats:
        total = Word.objects.filter(category=code).count()
        mastered = StudyProgress.objects.filter(word__category=code, status='mastered').count()
        learning = StudyProgress.objects.filter(word__category=code).exclude(
            status='new').exclude(status='mastered').count()
        cat_progress[code] = {
            'label': label, 'total': total, 'mastered': mastered, 'learning': learning,
        }

    streak = get_streak()

    # 状态分布
    status_dist = []
    for status_code, status_label in StudyProgress.STATUS_CHOICES:
        cnt = StudyProgress.objects.filter(status=status_code).count()
        status_dist.append({'status': status_code, 'label': status_label, 'count': cnt})

    return JsonResponse({
        'days': days_data,
        'summary': {
            'total_new': summary['total_new'] or 0,
            'total_reviewed': summary['total_reviewed'] or 0,
            'avg_correct_rate': round(summary['avg_correct'] or 0, 1),
            'total_duration': summary['total_duration'] or 0,
            'streak': streak,
        },
        'error_words': error_list,
        'category_progress': cat_progress,
        'level_distribution': status_dist,
    })


def _get_week_bounds():
    """返回本周一 ~ 本周日（自然周）。"""
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())  # 周一是 0
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _collect_report_summary(week_start, week_end):
    """收集自然周内的统计快照数据（不含 AI 评语）。"""
    today = timezone.localdate()
    actual_end = min(week_end, today)  # 未到周日时统计到今天

    # 周期内新学/复习（与 api_stats 同口径）
    new_words = StudyProgress.objects.filter(
        learned_date__gte=week_start, learned_date__lte=actual_end).count()
    reviewed_words = StudyProgress.objects.filter(
        last_review__date__gte=week_start, last_review__date__lte=actual_end,
        review_count__gt=0
    ).exclude(learned_date__gte=F('last_review__date')).count()

    # 打卡数据
    checkins = list(DailyCheckIn.objects.filter(
        date__gte=week_start, date__lte=actual_end))
    total_duration = sum(c.study_duration for c in checkins)
    today_total = sum(c.today_correct + c.today_wrong for c in checkins)
    today_correct = sum(c.today_correct for c in checkins)
    correct_rate = round(today_correct / today_total * 100, 1) if today_total else 0
    active_days = sum(1 for c in checkins if c.new_words_learned > 0 or c.words_reviewed > 0 or c.study_duration > 0)

    # 学习最多的一天
    best_day = None
    if checkins:
        best = max(checkins, key=lambda c: c.new_words_learned + c.words_reviewed)
        if best.new_words_learned + best.words_reviewed > 0:
            best_day = best.date.isoformat()

    # 词库总体掌握情况
    total_words = Word.objects.count()
    mastered_words = StudyProgress.objects.filter(status='mastered').count()
    learning_words = StudyProgress.objects.exclude(status='new').exclude(status='mastered').count()
    excluded_words = StudyProgress.objects.filter(is_excluded=True).count()
    not_learned = max(0, total_words - mastered_words - learning_words - excluded_words)
    mastery_rate = round(mastered_words / total_words * 100, 1) if total_words else 0

    # 完成度预测：按每日新词目标
    settings_obj = UserSettings.get_settings()
    daily_new_target = max(1, settings_obj.daily_new_target)
    days_to_finish = (not_learned + daily_new_target - 1) // daily_new_target
    finish_date = today + timedelta(days=days_to_finish)

    # 易错词 Top10
    weak_words = [{
        'word': e.word.word,
        'error_count': e.error_count,
    } for e in StudyProgress.objects.select_related('word')
        .filter(error_count__gt=0).order_by('-error_count')[:10]]

    # 陌生词性统计（uncommon_pos JSON）
    pos_counter = {}
    for p in StudyProgress.objects.exclude(uncommon_pos='[]').exclude(uncommon_pos=''):
        for pos in parse_uncommon_pos(p.uncommon_pos):
            pos_counter[pos] = pos_counter.get(pos, 0) + 1
    weak_pos = [{'pos': k, 'count': v} for k, v in
                sorted(pos_counter.items(), key=lambda x: -x[1])[:5]]

    return {
        'period_label': f'{week_start.isoformat()} ~ {week_end.isoformat()}',
        'week_start': week_start.isoformat(),
        'week_end': week_end.isoformat(),
        'actual_end': actual_end.isoformat(),
        'new_words': new_words,
        'reviewed_words': reviewed_words,
        'study_duration': total_duration,
        'correct_rate': correct_rate,
        'streak': get_streak(),
        'active_days': active_days,
        'best_day': best_day,
        'total_words': total_words,
        'mastered_words': mastered_words,
        'learning_words': learning_words,
        'not_learned': not_learned,
        'excluded_words': excluded_words,
        'mastery_rate': mastery_rate,
        'days_to_finish': days_to_finish,
        'finish_date': finish_date.isoformat(),
        'daily_new_target': daily_new_target,
        'weak_words': weak_words,
        'weak_pos': weak_pos,
    }


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_learning_report(request):
    """周学习报告：GET 查当前周报告与历史 / POST 生成（或重新生成）本周报告"""
    week_start, week_end = _get_week_bounds()

    if request.method == 'GET':
        current = LearningReport.objects.filter(week_start=week_start).first()
        history = [{
            'id': r.id,
            'week_start': r.week_start.isoformat(),
            'week_end': r.week_end.isoformat(),
            'summary': r.get_summary(),
            'ai_comment': r.ai_comment,
            'created_at': r.created_at.strftime('%Y-%m-%d %H:%M'),
        } for r in LearningReport.objects.all()[:20]]
        return JsonResponse({
            'success': True,
            'today': timezone.localdate().isoformat(),
            'is_sunday': timezone.localdate().weekday() == 6,
            'current': {
                'id': current.id,
                'week_start': current.week_start.isoformat(),
                'week_end': current.week_end.isoformat(),
                'summary': current.get_summary(),
                'ai_comment': current.ai_comment,
                'created_at': current.created_at.strftime('%Y-%m-%d %H:%M'),
            } if current else None,
            'history': history,
        })

    # POST：生成（或重新生成）本周报告
    try:
        settings_obj = UserSettings.get_settings()
        cfg = resolve_ai_model({'model_id': settings_obj.assistant_model_id} if settings_obj.assistant_model_id else {})
        summary = _collect_report_summary(week_start, week_end)
        prompt = weekly_report_prompt(json.dumps(summary, ensure_ascii=False))
        comment = _ai_chat_once(cfg, prompt, max_tokens=1000)
        report, _ = LearningReport.objects.update_or_create(
            week_start=week_start,
            defaults={
                'week_end': week_end,
                'summary_json': json.dumps(summary, ensure_ascii=False),
                'ai_comment': comment,
            },
        )
        return JsonResponse({
            'success': True,
            'id': report.id,
            'summary': summary,
            'ai_comment': comment,
            'created_at': report.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'生成失败：{e}'}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def api_study_duration(request):
    """累加当前学习页的有效前台时长（秒）。"""
    try:
        data = json.loads(request.body or '{}')
        seconds = int(data.get('seconds', 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': '时长格式错误'}, status=400)

    # 客户端每 20 秒同步一次；限制单次上报，避免异常请求造成统计失真。
    seconds = max(0, min(seconds, 90))
    if seconds == 0:
        return JsonResponse({'success': True, 'added': 0})

    checkin, _ = DailyCheckIn.objects.get_or_create(date=timezone.localdate())
    DailyCheckIn.objects.filter(pk=checkin.pk).update(study_duration=F('study_duration') + seconds)
    return JsonResponse({'success': True, 'added': seconds})


def api_export_pdf(request):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    export_type = request.GET.get('type', 'all')
    dictation_mode = request.GET.get('dictation', '')  # 'en2zh' or 'zh2en'
    unit_num = request.GET.get('unit')
    search = request.GET.get('search', '')
    category = request.GET.get('category', '')
    status = request.GET.get('status', '')

    # Build query based on filters
    if export_type == 'filtered':
        query = Word.objects.select_related('unit').all()
        if search:
            query = query.filter(Q(word__icontains=search) | Q(meanings__icontains=search))
        if category:
            query = query.filter(category=category)
        if unit_num:
            query = query.filter(unit__number=int(unit_num))
        if status:
            query = query.filter(progress__status=status)
        words = query.order_by('unit__number', 'list_number')
        title_text = '考研单词表（筛选结果）'
    elif export_type == 'unit' and unit_num:
        words = Word.objects.filter(unit__number=int(unit_num)).order_by('list_number')
        unit_obj = Unit.objects.filter(number=int(unit_num)).first()
        title_text = f'考研单词表 - {unit_obj.name if unit_obj else "Unit "+unit_num}'
    elif export_type == 'favorites':
        words = Word.objects.filter(favorite__isnull=False).order_by('unit__number')
        title_text = '考研单词表（收藏单词）'
    elif export_type == 'errors':
        words = Word.objects.filter(progress__error_count__gt=0).order_by('-progress__error_count')
        title_text = '考研单词表（易错词）'
    else:
        words = Word.objects.all().order_by('unit__number', 'list_number')
        title_text = '考研单词表（全部）'

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()

    # 默写纸模式
    if dictation_mode:
        if dictation_mode == 'en2zh':
            title_text = f'{title_text} - 默写纸（看英文写中文）'
        else:
            title_text = f'{title_text} - 默写纸（看中文写英文）'

        title_style = ParagraphStyle('title', fontName='STSong-Light', fontSize=14,
                                     leading=20, spaceAfter=10, alignment=1)

        elements = [Paragraph(title_text, title_style),
                    Spacer(1, 6 * mm)]

        table_data = []
        if dictation_mode == 'en2zh':
            # 看英文写中文：显示英文，中文留空
            table_data.append(['序号', '单词', '词性', '中文释义（默写）'])
            for i, w in enumerate(words, 1):
                table_data.append([
                    str(i),
                    w.word,
                    w.pos or '',
                    '',  # 留空供默写
                ])
        else:
            # 看中文写英文：显示中文，英文留空
            table_data.append(['序号', '中文释义', '词性', '单词（默写）'])
            for i, w in enumerate(words, 1):
                meanings_str = '; '.join(w.get_meanings()[:3])
                table_data.append([
                    str(i),
                    meanings_str,
                    w.pos or '',
                    '',  # 留空供默写
                ])

        if len(table_data) > 1:
            # 根据模式调整列宽
            if dictation_mode == 'en2zh':
                col_widths = [14 * mm, 50 * mm, 18 * mm, 78 * mm]
            else:
                col_widths = [14 * mm, 68 * mm, 18 * mm, 60 * mm]

            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'STSong-Light'),  # 全部使用STSong-Light以支持音标
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(t)
        else:
            cn_style = ParagraphStyle('cn', fontName='STSong-Light', fontSize=10,
                                      leading=16, spaceAfter=4)
            elements.append(Paragraph('暂无单词数据', cn_style))

        doc.build(elements)
        buf.seek(0)

        filename = f'hongbaoshu_{export_type}_dictation.pdf'
        return FileResponse(buf, content_type='application/pdf',
                            filename=filename, as_attachment=True)

    # 正常导出模式（包含音标）
    title_style = ParagraphStyle('title', fontName='STSong-Light', fontSize=14,
                                 leading=20, spaceAfter=10, alignment=1)

    elements = [Paragraph(title_text, title_style),
                Spacer(1, 6 * mm)]

    total_rows = len(words)
    table_data = []
    table_data.append(['序号', '单词', '词性', '释义'])
    for i, w in enumerate(words, 1):
        meanings_str = '; '.join(w.get_meanings()[:3])
        table_data.append([
            str(i),
            w.word,
            w.pos or '',
            meanings_str,
        ])

    if len(table_data) > 1:
        col_widths = [14 * mm, 50 * mm, 18 * mm, 78 * mm]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'STSong-Light'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t)
    else:
        cn_style = ParagraphStyle('cn', fontName='STSong-Light', fontSize=10,
                                  leading=16, spaceAfter=4)
        elements.append(Paragraph('暂无单词数据', cn_style))

    doc.build(elements)
    buf.seek(0)

    filename = f'hongbaoshu_{export_type}.pdf'
    return FileResponse(buf, content_type='application/pdf',
                        filename=filename, as_attachment=True)


def api_backup(request):
    from django.core.serializers.json import DjangoJSONEncoder

    settings_obj = UserSettings.get_settings()
    data = {
        'version': '1.0',
        'exported_at': timezone.localtime().isoformat(),
        'settings': {
            'font_size': settings_obj.font_size,
            'dark_mode': settings_obj.dark_mode,
            'pronunciation_on': settings_obj.pronunciation_on,
            'auto_read': settings_obj.auto_read,
            'speech_rate': settings_obj.speech_rate,
            'voice_type': settings_obj.voice_type,
            'daily_new_target': settings_obj.daily_new_target,
            'daily_review_target': settings_obj.daily_review_target,
        },
        'progress': [
            {
                'word_id': p.word_id,
                'status': p.status,
                'mastery_level': p.mastery_level,
                'review_count': p.review_count,
                'error_count': p.error_count,
                'last_review': p.last_review.isoformat() if p.last_review else None,
                'next_review': p.next_review.isoformat() if p.next_review else None,
                'is_today_new': p.is_today_new,
                'learned_date': p.learned_date.isoformat() if p.learned_date else None,
            }
            for p in StudyProgress.objects.all()
        ],
        'plans': [
            {
                'name': p.name,
                'daily_new_words': p.daily_new_words,
                'daily_review_count': p.daily_review_count,
                'target_date': p.target_date.isoformat() if p.target_date else None,
                'unit_range': p.unit_range,
                'is_active': p.is_active,
                'start_date': p.start_date.isoformat(),
            }
            for p in StudyPlan.objects.all()
        ],
        'checkins': [
            {
                'date': c.date.isoformat(),
                'new_words_learned': c.new_words_learned,
                'words_reviewed': c.words_reviewed,
                'study_duration': c.study_duration,
                'correct_rate': c.correct_rate,
                'is_checked': c.is_checked,
            }
            for c in DailyCheckIn.objects.all()
        ],
        'favorites': [
            {
                'word_id': f.word_id,
                'created_at': timezone.localtime(f.created_at).isoformat(),
            }
            for f in Favorite.objects.all()
        ],
        'notes': [
            {
                'word_id': n.word_id,
                'content': n.content,
                'page_number': n.page_number,
            }
            for n in Note.objects.all()
        ],
    }

    os.makedirs(settings.BACKUP_DIR, exist_ok=True)
    filename = f'backup_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
    filepath = os.path.join(settings.BACKUP_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, cls=DjangoJSONEncoder)

    response = HttpResponse(
        json.dumps(data, ensure_ascii=False, cls=DjangoJSONEncoder),
        content_type='application/json; charset=utf-8',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
@require_http_methods(['POST'])
def api_restore(request):
    try:
        # 支持直接上传 JSON 文件或通过 body 发送 JSON
        if request.FILES.get('file'):
            content = request.FILES['file'].read().decode('utf-8')
        else:
            content = request.body.decode('utf-8')
        data = json.loads(content)

        # 恢复设置
        if 'settings' in data:
            s = data['settings']
            settings_obj = UserSettings.get_settings()
            for k, v in s.items():
                setattr(settings_obj, k, v)
            settings_obj.save()

        # 恢复进度
        if 'progress' in data:
            # 先清空
            StudyProgress.objects.all().delete()
            for p in data['progress']:
                StudyProgress.objects.create(
                    word_id=p['word_id'],
                    status=p.get('status', 'new'),
                    mastery_level=p.get('mastery_level', 0),
                    review_count=p.get('review_count', 0),
                    error_count=p.get('error_count', 0),
                    is_today_new=p.get('is_today_new', False),
                    learned_date=p.get('learned_date'),
                )

        # 恢复打卡
        if 'checkins' in data:
            DailyCheckIn.objects.all().delete()
            for c in data['checkins']:
                DailyCheckIn.objects.create(**c)

        # 恢复收藏
        if 'favorites' in data:
            Favorite.objects.all().delete()
            for f in data['favorites']:
                Favorite.objects.create(word_id=f['word_id'])

        # 恢复笔记
        if 'notes' in data:
            Note.objects.all().delete()
            for n in data['notes']:
                Note.objects.create(word_id=n['word_id'], content=n.get('content', ''),
                                    page_number=n.get('page_number'))

        # 恢复计划
        if 'plans' in data:
            StudyPlan.objects.all().delete()
            for p in data['plans']:
                StudyPlan.objects.create(**p)

        return JsonResponse({'success': True, 'message': '恢复完成'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_settings(request):
    if request.method == 'GET':
        settings_obj = UserSettings.get_settings()
        return JsonResponse({
            'success': True,
            'assistant_model_id': settings_obj.assistant_model_id,
            'recognize_model_id': settings_obj.recognize_model_id,
            'review_model_id': settings_obj.review_model_id,
            'quick_memory_model_id': settings_obj.quick_memory_model_id,
            'meaning_check_model_id': settings_obj.meaning_check_model_id,
            'use_ai_meaning_check': settings_obj.use_ai_meaning_check,
        })
    try:
        data = json.loads(request.body)
        settings_obj = UserSettings.get_settings()
        for k, v in data.items():
            if not hasattr(settings_obj, k):
                continue
            field = settings_obj._meta.get_field(k)
            if field.is_relation and field.many_to_one:
                if v is None or v == '':
                    setattr(settings_obj, k, None)
                else:
                    try:
                        setattr(settings_obj, k, field.related_model.objects.get(pk=int(v)))
                    except (field.related_model.DoesNotExist, ValueError, TypeError):
                        return JsonResponse({'error': '指定的模型不存在'}, status=400)
            else:
                setattr(settings_obj, k, v)
        settings_obj.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST', 'DELETE'])
def api_note(request, word_id):
    word = get_object_or_404(Word, id=word_id)
    if request.method == 'GET':
        note = Note.objects.filter(word=word).first()
        return JsonResponse({
            'success': True,
            'content': note.content if note else '',
            'page_number': note.page_number if note else None,
            'updated_at': timezone.localtime(note.updated_at).strftime('%Y-%m-%d %H:%M') if note and note.updated_at else None,
        })
    if request.method == 'DELETE':
        Note.objects.filter(word=word).delete()
        return JsonResponse({'success': True, 'deleted': True})
    try:
        data = json.loads(request.body)
        note, created = Note.objects.get_or_create(word=word)
        note.content = data.get('content', '')
        note.page_number = data.get('page_number')
        if note.page_number == '':
            note.page_number = None
        note.save()
        return JsonResponse({'success': True, 'note_id': note.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST', 'DELETE'])
def api_quick_memory(request, word_id):
    """速记：增删改查（GET 查询 / POST 保存编辑 / DELETE 删除），内容存数据库"""
    word = get_object_or_404(Word, id=word_id)
    if request.method == 'GET':
        qm = QuickMemory.objects.filter(word=word).first()
        return JsonResponse({
            'success': True,
            'content': qm.content if qm else '',
            'updated_at': timezone.localtime(qm.updated_at).strftime('%Y-%m-%d %H:%M') if qm and qm.updated_at else None,
        })
    if request.method == 'DELETE':
        QuickMemory.objects.filter(word=word).delete()
        return JsonResponse({'success': True, 'deleted': True})
    try:
        data = json.loads(request.body)
        qm, _ = QuickMemory.objects.get_or_create(word=word)
        qm.content = data.get('content', '')
        qm.save()
        return JsonResponse({'success': True, 'quick_memory_id': qm.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_quick_memory_generate(request, word_id):
    """AI 生成速记：数据库已有缓存则直接返回（不再调用 AI）；force=true 时强制重新生成"""
    word = get_object_or_404(Word, id=word_id)
    try:
        data = json.loads(request.body)
    except Exception:
        data = {}

    existing = QuickMemory.objects.filter(word=word).first()
    if existing and existing.content and not data.get('force'):
        return JsonResponse({'success': True, 'content': existing.content, 'cached': True})

    settings_obj = UserSettings.get_settings()
    if settings_obj.quick_memory_model and not data.get('model_id'):
        data['model_id'] = settings_obj.quick_memory_model_id

    try:
        cfg = resolve_ai_model(data)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    api_key = cfg['api_key']
    base_url = cfg['base_url']
    endpoint = cfg['endpoint']
    model = cfg['model_id']

    word_text = word.word
    pos = word.pos or ''
    meanings = '；'.join(word.get_meanings()[:3]) or ''
    phonetic_us = word.phonetic_us or ''
    phonetic_uk = word.phonetic_uk or ''

    prompt = quick_memory_prompt(word_text, pos, meanings, phonetic_us, phonetic_uk)

    payload = {
        'model': model,
        'temperature': 0.4,
        'max_tokens': 500,
        'messages': [{'role': 'user', 'content': prompt}],
    }

    req = urllib.request.Request(
        resolve_ai_endpoint(base_url, endpoint),
        data=json.dumps(payload).encode('utf-8'),
        headers=build_ai_headers(api_key),
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'ignore')
        return JsonResponse({'error': 'AI 接口错误 (HTTP %s): %s' % (e.code, body[:400])}, status=502)
    except urllib.error.URLError as e:
        return JsonResponse({'error': '无法连接 %s: %s' % (resolve_ai_endpoint(base_url, endpoint), e.reason)}, status=502)

    content = (result.get('choices', [{}])[0].get('message', {}).get('content', '') or '').strip()
    if not content:
        return JsonResponse({'error': 'AI 未返回有效内容'}, status=502)

    qm, _ = QuickMemory.objects.get_or_create(word=word)
    qm.content = content
    qm.save()
    return JsonResponse({'success': True, 'content': content, 'cached': False})


@csrf_exempt
@require_http_methods(['GET', 'POST', 'DELETE'])
def api_assistant(request):
    """小助手：GET 获取对话历史 / POST 提问（AI 回答，历史互通） / DELETE 清空历史"""
    if request.method == 'GET':
        msgs = ChatMessage.objects.all().order_by('id')
        return JsonResponse({
            'success': True,
            'messages': [
                {
                    'id': m.id,
                    'role': m.role,
                    'content': m.content,
                    'word_id': m.word_id,
                    'created_at': timezone.localtime(m.created_at).strftime('%Y-%m-%d %H:%M'),
                }
                for m in msgs
            ],
        })

    if request.method == 'DELETE':
        ChatMessage.objects.all().delete()
        return JsonResponse({'success': True})

    # ---- POST：问答 ----
    try:
        data = json.loads(request.body)
    except Exception:
        data = {}
    user_text = (data.get('message') or '').strip()
    if not user_text:
        return JsonResponse({'error': '消息不能为空'}, status=400)

    word = None
    word_id = data.get('word_id')
    if word_id:
        try:
            word = Word.objects.get(id=int(word_id))
        except (Word.DoesNotExist, ValueError, TypeError):
            word = None

    # 校验 AI 配置（未配置时直接提示，不写入历史）
    # 优先使用设置页指定的小助手模型；未指定时自动使用第一个启用的模型
    settings_obj = UserSettings.get_settings()
    if settings_obj.assistant_model:
        data = dict(data)
        data['model_id'] = settings_obj.assistant_model_id
    try:
        cfg = resolve_ai_model(data)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)

    # 构造上下文：系统提示 + 当前单词信息 + 最近对话历史
    system_prompt = ASSISTANT_SYSTEM_PROMPT
    messages = [{'role': 'system', 'content': system_prompt}]

    if word:
        word_ctx = assistant_word_context(word)
        messages.append({'role': 'system', 'content': word_ctx})

    # 最近 20 条历史作为对话上下文（记忆互通）
    for m in ChatMessage.objects.all().order_by('-id')[:20][::-1]:
        messages.append({'role': m.role, 'content': m.content[:2000]})

    messages.append({'role': 'user', 'content': user_text})

    payload = {
        'model': cfg['model_id'],
        'temperature': 0.7,
        'max_tokens': 1000,
        'messages': messages,
    }

    req = urllib.request.Request(
        resolve_ai_endpoint(cfg['base_url'], cfg['endpoint']),
        data=json.dumps(payload).encode('utf-8'),
        headers=build_ai_headers(cfg['api_key']),
        method='POST',
    )

    # 先保存用户消息；AI 调用失败时回滚，保证历史里只有成功的问答
    user_msg = ChatMessage.objects.create(
        role='user', content=user_text, word_id=word.id if word else None)

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'ignore')
        user_msg.delete()
        return JsonResponse({'error': 'AI 接口错误 (HTTP %s): %s' % (e.code, body[:400])}, status=502)
    except urllib.error.URLError as e:
        user_msg.delete()
        return JsonResponse({'error': '无法连接 %s: %s' % (resolve_ai_endpoint(cfg['base_url'], cfg['endpoint']), e.reason)}, status=502)

    content = (result.get('choices', [{}])[0].get('message', {}).get('content', '') or '').strip()
    if not content:
        user_msg.delete()
        return JsonResponse({'error': 'AI 未返回有效内容'}, status=502)

    ai_msg = ChatMessage.objects.create(
        role='assistant', content=content, word_id=word.id if word else None)

    def _ser(m):
        return {
            'id': m.id,
            'role': m.role,
            'content': m.content,
            'word_id': m.word_id,
            'created_at': timezone.localtime(m.created_at).strftime('%Y-%m-%d %H:%M'),
        }

    return JsonResponse({'success': True, 'user_message': _ser(user_msg), 'assistant_message': _ser(ai_msg)})


def ai_chat_page(request):
    """AI 智能助手独立页面：全屏对话 + 文件上传 + 模型选择"""
    models = AIModel.objects.filter(enabled=True).order_by('id')
    settings_obj = UserSettings.get_settings()
    current_model = settings_obj.assistant_model or models.first()
    return render(request, 'ai_chat.html', {
        'models': models,
        'current_model': current_model,
    })


def _ser_chat_msg(m):
    """ChatMessage → 前端 JSON"""
    return {
        'id': m.id,
        'role': m.role,
        'content': m.content,
        'attachments': m.attachments or [],
        'created_at': timezone.localtime(m.created_at).strftime('%Y-%m-%d %H:%M'),
    }


def _ser_conversation(c):
    """Conversation → 前端 JSON"""
    return {
        'id': c.id,
        'title': c.title,
        'message_count': ChatMessage.objects.filter(conversation_id=c.id).count(),
        'updated_at': timezone.localtime(c.updated_at).strftime('%m-%d %H:%M'),
    }


def api_ai_chat(request):
    """AI 智能助手 API（多会话）：
    GET    /api/ai/chat/                     → 启用模型列表 + 会话列表 + 最近会话的消息
    GET    /api/ai/chat/?conversation_id=X   → 指定会话的消息
    POST   /api/ai/chat/                     → 发送消息（conversation_id 缺省时自动新建会话）
    DELETE /api/ai/chat/?conversation_id=X   → 清空指定会话的记录；缺省清空全部
    """
    if request.method == 'GET':
        models = AIModel.objects.filter(enabled=True).order_by('id')
        conversations = Conversation.objects.all()

        conv_id = request.GET.get('conversation_id')
        if conv_id:
            try:
                current_conv = Conversation.objects.get(id=int(conv_id))
            except (Conversation.DoesNotExist, ValueError, TypeError):
                current_conv = conversations.first()
        else:
            current_conv = conversations.first()

        if current_conv:
            msgs = ChatMessage.objects.filter(conversation_id=current_conv.id).order_by('id')
        else:
            msgs = ChatMessage.objects.none()

        return JsonResponse({
            'success': True,
            'models': [serialize_ai_model(m) for m in models],
            'conversations': [_ser_conversation(c) for c in conversations],
            'current_conversation_id': current_conv.id if current_conv else None,
            'messages': [_ser_chat_msg(m) for m in msgs],
        })

    if request.method == 'DELETE':
        conv_id = request.GET.get('conversation_id')
        if conv_id:
            try:
                conv = Conversation.objects.get(id=int(conv_id))
            except (Conversation.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'error': '会话不存在'}, status=404)
            ChatMessage.objects.filter(conversation_id=conv.id).delete()
        else:
            ChatMessage.objects.all().delete()
        return JsonResponse({'success': True})

    # ---- POST：对话 ----
    try:
        data = json.loads(request.body)
    except Exception:
        data = {}
    user_text = (data.get('message') or '').strip()
    if not user_text and not data.get('files'):
        return JsonResponse({'error': '消息不能为空'}, status=400)

    # 会话：指定 ID 则复用，否则新建
    conv_id = data.get('conversation_id')
    conv = None
    if conv_id:
        try:
            conv = Conversation.objects.get(id=int(conv_id))
        except (Conversation.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': '会话不存在，请刷新重试'}, status=404)
    if conv is None:
        conv = Conversation.objects.create(
            title=(user_text or '（文件）')[:30] or '新对话')

    # 模型选择：前端指定 model_id（数据库记录）> 设置页小助手模型 > 第一个启用模型
    settings_obj = UserSettings.get_settings()
    chosen_id = data.get('model_id')
    if not chosen_id and settings_obj.assistant_model_id:
        chosen_id = settings_obj.assistant_model_id
    try:
        cfg = resolve_ai_model({'model_id': chosen_id} if chosen_id else {})
    except ValueError as e:
        conv.delete()  # 新建但模型不可用 → 回滚会话
        return JsonResponse({'error': str(e)}, status=400)

    # 解析文件附件：图片 → data URI（视觉模型）；文本/其它 → 截断文本
    files = data.get('files') or []
    content_parts = []
    file_notes = []
    for f in files[:8]:  # 最多 8 个附件
        name = (f.get('name') or '附件').strip()[:120]
        mime = (f.get('mime') or '').lower()
        raw = f.get('content') or ''
        if mime.startswith('image/') and raw:
            content_parts.append({
                'type': 'image_url',
                'image_url': {'url': 'data:%s;base64,%s' % (mime, raw)},
            })
            file_notes.append({'name': name, 'type': 'image', 'mime': mime})
        else:
            try:
                text = raw if isinstance(raw, str) else base64.b64decode(raw).decode('utf-8', 'ignore')
            except Exception:
                text = ''
            text = text[:50000]
            content_parts.append({'type': 'text', 'text': '【文件：%s】\n%s' % (name, text)})
            file_notes.append({'name': name, 'type': 'text'})

    if user_text:
        content_parts.append({'type': 'text', 'text': user_text})
    if not content_parts:
        return JsonResponse({'error': '无法解析附件内容'}, status=400)

    # 构造消息链：系统提示 + 本会话最近 20 条历史 + 当前消息（含附件）
    messages = [{'role': 'system', 'content': ASSISTANT_SYSTEM_PROMPT}]
    for m in ChatMessage.objects.filter(conversation_id=conv.id).order_by('-id')[:20][::-1]:
        messages.append({'role': m.role, 'content': m.content[:2000]})

    user_msg = ChatMessage.objects.create(
        role='user',
        content=user_text or '（已发送 %d 个文件）' % len(file_notes),
        conversation_id=conv.id,
        attachments=file_notes,
    )

    payload = {
        'model': cfg['model_id'],
        'temperature': 0.7,
        'max_tokens': 2000,
        'messages': messages + [{'role': 'user', 'content': content_parts}],
    }

    req = urllib.request.Request(
        resolve_ai_endpoint(cfg['base_url'], cfg['endpoint']),
        data=json.dumps(payload).encode('utf-8'),
        headers=build_ai_headers(cfg['api_key']),
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'ignore')
        user_msg.delete()
        if not ChatMessage.objects.filter(conversation_id=conv.id).exists():
            conv.delete()  # 新建会话无消息 → 回滚
        return JsonResponse({'error': 'AI 接口错误 (HTTP %s): %s' % (e.code, body[:400])}, status=502)
    except urllib.error.URLError as e:
        user_msg.delete()
        if not ChatMessage.objects.filter(conversation_id=conv.id).exists():
            conv.delete()
        return JsonResponse({'error': '无法连接 AI 服务: %s' % e.reason}, status=502)

    content = (result.get('choices', [{}])[0].get('message', {}).get('content', '') or '').strip()
    if not content:
        user_msg.delete()
        if not ChatMessage.objects.filter(conversation_id=conv.id).exists():
            conv.delete()
        return JsonResponse({'error': 'AI 未返回有效内容'}, status=502)

    ai_msg = ChatMessage.objects.create(
        role='assistant', content=content, conversation_id=conv.id)

    return JsonResponse({
        'success': True,
        'conversation': _ser_conversation(conv),
        'user_message': _ser_chat_msg(user_msg),
        'assistant_message': _ser_chat_msg(ai_msg),
    })


@require_http_methods(['POST'])
def api_ai_chat_new(request):
    """新建 AI 会话"""
    conv = Conversation.objects.create(title='新对话')
    return JsonResponse({'success': True, 'conversation': _ser_conversation(conv)})


@require_http_methods(['DELETE'])
def api_ai_chat_delete(request, conv_id):
    """删除 AI 会话（连同其消息记录）"""
    try:
        conv = Conversation.objects.get(id=conv_id)
    except Conversation.DoesNotExist:
        return JsonResponse({'error': '会话不存在'}, status=404)
    ChatMessage.objects.filter(conversation_id=conv.id).delete()
    conv.delete()
    return JsonResponse({'success': True})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_assistant_model(request):
    """小助手模型配置：GET 查询当前指定 / POST 设置（null = 自动使用第一个启用模型）"""
    settings_obj = UserSettings.get_settings()

    if request.method == 'GET':
        m = settings_obj.assistant_model
        return JsonResponse({
            'assistant_model_id': m.id if m else None,
            'assistant_model_name': (m.display_name or m.model_id) if m else None,
        })

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '请求格式错误'}, status=400)

    mid = data.get('model_id')
    if mid:
        try:
            m = AIModel.objects.get(id=int(mid))
        except (AIModel.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': '模型不存在'}, status=404)
        if not m.enabled:
            return JsonResponse({'error': '该模型已被禁用，请先启用'}, status=400)
        settings_obj.assistant_model = m
    else:
        settings_obj.assistant_model = None
    settings_obj.save()

    cur = settings_obj.assistant_model
    return JsonResponse({
        'success': True,
        'assistant_model_id': cur.id if cur else None,
        'assistant_model_name': (cur.display_name or cur.model_id) if cur else None,
    })


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def api_favorite(request, word_id):
    word = get_object_or_404(Word, id=word_id)
    if request.method == 'DELETE':
        Favorite.objects.filter(word=word).delete()
        return JsonResponse({'success': True, 'is_favorite': False})
    fav, created = Favorite.objects.get_or_create(word=word)
    if not created:
        fav.delete()
        return JsonResponse({'success': True, 'is_favorite': False})
    return JsonResponse({'success': True, 'is_favorite': True})


def api_learn_words(request):
    """返回按 scope+units 筛选的单词列表（与 learn_session 逻辑一致）"""
    scope = request.GET.get('scope', 'unknown')
    unit_ids = request.GET.getlist('units')

    query = Word.objects.all()
    if unit_ids:
        query = query.filter(unit__number__in=unit_ids)

    # 永不忘记的词不再出现
    query = query.exclude(progress__is_excluded=True)

    if scope == 'mastered':
        query = query.filter(progress__status='mastered')
    else:
        query = query.exclude(progress__status='mastered')

    mode = request.GET.get('mode', 'sequential')
    words = list(query)

    if mode == 'random':
        random.shuffle(words)
    else:
        words = sorted(words, key=lambda w: (w.unit.number, w.list_number))

    # 批量预取进度，避免 N+1
    word_ids = [w.id for w in words]
    progress_map = {
        p.word_id: p for p in StudyProgress.objects.filter(word_id__in=word_ids)
    }

    word_data = []
    for w in words:
        p = progress_map.get(w.id)
        word_data.append({
            'id': w.id,
            'word': w.word,
            'phonetic_us': w.phonetic_us,
            'pos': w.pos,
            'meanings': w.get_meanings(),
            'meanings_by_pos': w.get_meanings_by_pos(),
            'example_en': w.example_en,
            'example_zh': w.example_zh,
            'unit_number': w.unit.number if w.unit else None,
            'uncommon_pos': parse_uncommon_pos(p.uncommon_pos if p else None),
        })

    return JsonResponse({'words': word_data, 'total': len(word_data)})


def api_exam_words(request):
    """生成模拟考试题目（4选1选择题，不返回答案给前端）"""
    scope = request.GET.get('scope', 'all')
    unit_ids = request.GET.getlist('units')
    category = request.GET.get('category', '')
    direction = request.GET.get('direction', 'en2zh')
    try:
        count = int(request.GET.get('count', 20))
    except (TypeError, ValueError):
        count = 20

    query = Word.objects.all()
    if unit_ids:
        query = query.filter(unit__number__in=unit_ids)
    if category:
        query = query.filter(category=category)

    if scope == 'unknown':
        query = query.exclude(progress__status='mastered')
    elif scope == 'mastered':
        query = query.filter(progress__status='mastered')
    elif scope == 'favorites':
        query = query.filter(favorite__isnull=False)
    elif scope == 'errors':
        query = query.filter(progress__error_count__gt=0)
    # 'all'：全部单词

    words = list(query)
    random.shuffle(words)
    if count > 0 and len(words) > count:
        words = words[:count]

    # 干扰项候选池
    all_words = list(Word.objects.all())
    en_pool = [w.word for w in all_words]
    zh_pool = []
    for w in all_words:
        for m in w.get_meanings():
            zh_pool.append(m)

    questions = []
    for w in words:
        meanings = w.get_meanings()
        if direction == 'spelling':
            # 拼写默写：看中文写英文（本地判定）
            questions.append({
                'id': w.id,
                'word': w.word,
                'phonetic_us': w.phonetic_us,
                'pos': w.pos,
                'prompt': '；'.join(meanings) if meanings else w.word,
                'options': [],
                'correct_index': None,
                'type': 'spelling',
            })
            continue
        if direction == 'meaning':
            # 释义默写：看英文写中文（AI 判定）
            questions.append({
                'id': w.id,
                'word': w.word,
                'phonetic_us': w.phonetic_us,
                'pos': w.pos,
                'prompt': w.word,
                'options': [],
                'correct_index': None,
                'type': 'meaning',
            })
            continue
        if direction == 'en2zh':
            if not meanings:
                continue
            # 正确选项只取单个释义，避免"一长串=正确答案"被看穿
            correct = meanings[0]
            candidates = [m for m in zh_pool if m != correct]
            distractors = random.sample(candidates, 3) if len(candidates) >= 3 else candidates
            options = list(distractors) + [correct]
        else:
            correct = w.word
            candidates = [x for x in en_pool if x != correct]
            distractors = random.sample(candidates, 3) if len(candidates) >= 3 else candidates
            options = list(distractors) + [correct]
        random.shuffle(options)
        correct_index = options.index(correct)
        questions.append({
            'id': w.id,
            'word': w.word,
            'phonetic_us': w.phonetic_us,
            'pos': w.pos,
            'prompt': w.word if direction == 'en2zh'
                      else ('；'.join(meanings) if meanings else w.word),
            'options': options,
            'correct_index': correct_index,
            'type': 'choice',
        })

    # 存入 session 供交卷时评分
    request.session['exam_direction'] = direction
    request.session['exam_questions'] = [
        {'id': q['id'], 'options': q['options'], 'correct_index': q['correct_index'], 'type': q.get('type', 'choice')}
        for q in questions
    ]

    # 返回前移除答案字段
    for q in questions:
        q.pop('correct_index', None)

    return JsonResponse({'questions': questions, 'direction': direction, 'total': len(questions)})


@csrf_exempt
@require_http_methods(['POST'])
def api_exam_submit(request):
    """交卷评分：更新会/不会状态、记录会话、更新统计"""
    try:
        data = json.loads(request.body)
        answers = data.get('answers', [])
        try:
            duration = int(data.get('duration', 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        stored = request.session.get('exam_questions', [])

        if not stored:
            return JsonResponse({'error': '考试已过期，请重新开始'}, status=400)

        answer_map = {a['word_id']: a for a in answers}

        today = timezone.localdate()
        now = timezone.now()
        checkin, _ = DailyCheckIn.objects.get_or_create(date=today)

        results = []
        correct_count = 0
        for sq in stored:
            qid = sq['id']
            qtype = sq.get('type', 'choice')
            ans = answer_map.get(qid) or {}
            word = Word.objects.filter(id=qid).first()
            is_correct = False
            comment = ''

            if qtype == 'spelling':
                text = (ans.get('answer') or '').strip()
                is_correct = bool(word) and bool(text) and _normalize_spelling(text) == _normalize_spelling(word.word)
            elif qtype == 'meaning':
                text = (ans.get('answer') or '').strip()
                if word:
                    verdict, comment, _used = _judge_meaning_answer(word, text, data)
                    is_correct = verdict == 'correct'
            else:
                correct_index = sq['correct_index']
                selected = ans.get('selected')
                is_correct = (selected == correct_index)

            if is_correct:
                correct_count += 1

            if word:
                progress, _ = StudyProgress.objects.get_or_create(word=word)
                if progress.status == 'new':
                    progress.learned_date = today
                    progress.is_today_new = True
                if qtype == 'spelling':
                    progress.spelling_attempts += 1
                    if is_correct:
                        progress.spelling_correct += 1
                elif qtype == 'meaning':
                    progress.meaning_attempts += 1
                    if is_correct:
                        progress.meaning_correct += 1
                if is_correct:
                    # 答对 → 会
                    progress.mastery_level = 5
                    progress.status = 'mastered'
                    checkin.today_correct += 1
                else:
                    # 答错（含未作答）→ 不会
                    progress.mastery_level = 0
                    progress.status = 'learning'
                    progress.error_count += 1
                    checkin.today_wrong += 1
                progress.review_count += 1
                progress.last_review = now
                progress.save()
                results.append({
                    'word_id': qid,
                    'word': word.word,
                    'meanings': word.get_meanings(),
                    'correct': is_correct,
                    'selected_index': ans.get('selected'),
                    'correct_index': sq.get('correct_index'),
                    'type': qtype,
                    'comment': comment,
                    'answer': ans.get('answer') or '',
                })
            else:
                results.append({
                    'word_id': qid, 'word': '?', 'meanings': [],
                    'correct': is_correct, 'selected_index': ans.get('selected'),
                    'correct_index': sq.get('correct_index'),
                    'type': qtype,
                    'answer': ans.get('answer') or '',
                })

        checkin.save()
        auto_checked = update_daily_checkin()

        total = len(stored)
        StudySession.objects.create(
            date=today,
            mode='exam',
            end_time=now,
            words_count=total,
            correct_count=correct_count,
        )

        # 清除本次考试数据
        request.session.pop('exam_direction', None)
        request.session.pop('exam_questions', None)

        return JsonResponse({
            'success': True,
            'total': total,
            'correct_count': correct_count,
            'wrong_count': total - correct_count,
            'correct_rate': round(correct_count / total * 100, 1) if total else 0,
            'duration': duration,
            'results': results,
            'auto_checked': auto_checked,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def api_units(request):
    units = Unit.objects.annotate(
        mastered=Count('words__progress', filter=Q(words__progress__status='mastered'))
    ).all()
    data = []
    for u in units:
        data.append({
            'number': u.number,
            'name': u.name,
            'category': u.category,
            'category_display': u.get_category_display(),
            'word_count': u.word_count,
            'mastered_count': u.mastered_count(),
            'progress_percent': u.progress_percent(),
        })
    return JsonResponse({'units': data})


@csrf_exempt
@require_http_methods(['POST'])
def api_unit_create(request):
    """创建新单元（词汇类别可为必考/基础/超纲，也支持自定义）"""
    try:
        data = json.loads(request.body)
        number = int(data.get('number', 0))
        name = data.get('name', '').strip()
        category = (data.get('category') or 'required').strip()

        if not name:
            return JsonResponse({'error': '单元名称不能为空'}, status=400)
        if not category or len(category) > 20:
            return JsonResponse({'error': '词汇类别不能超过20个字符'}, status=400)
        if Unit.objects.filter(number=number).exists():
            return JsonResponse({'error': f'单元编号 {number} 已存在'}, status=400)

        unit = Unit.objects.create(
            number=number,
            name=name,
            category=category,
            word_count=0,
        )
        return JsonResponse({
            'success': True,
            'unit': {
                'id': unit.id,
                'number': unit.number,
                'name': unit.name,
                'category': unit.category,
                'word_count': unit.word_count,
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def api_unit_delete(request, unit_number):
    """删除单元及其所有单词"""
    try:
        unit = get_object_or_404(Unit, number=unit_number)
        word_count = unit.words.count()
        unit_name = unit.name
        unit.delete()
        return JsonResponse({
            'success': True,
            'message': f'已删除单元 {unit_name}（含 {word_count} 个单词）',
            'deleted_words': word_count,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_unit_update(request, unit_number):
    """更新单元信息"""
    try:
        data = json.loads(request.body)
        unit = get_object_or_404(Unit, number=unit_number)
        new_name = data.get('name', '').strip()
        new_category = (data.get('category') or '').strip()

        if not new_name:
            return JsonResponse({'error': '单元名称不能为空'}, status=400)

        unit.name = new_name
        if new_category:
            if new_category == '__custom__':
                return JsonResponse({'error': '词汇类别无效'}, status=400)
            if len(new_category) > 20:
                return JsonResponse({'error': '词汇类别不能超过20个字符'}, status=400)
            unit.category = new_category
        unit.save()

        return JsonResponse({
            'success': True,
            'unit': {
                'number': unit.number,
                'name': unit.name,
                'category': unit.category,
                'word_count': unit.word_count,
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ─── 手动添加 / AI 导入单词 ────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def api_word_create(request):
    """手动添加或 AI 导入单词（统一走规范化层）"""
    try:
        data = json.loads(request.body)
        nd = normalize_word_data(data)
        if not nd:
            return JsonResponse({'error': '单词不能为空'}, status=400)

        # 如果单词已存在，返回已存在信息
        existing = Word.objects.filter(word__iexact=nd['word']).first()
        if existing:
            return JsonResponse({'error': '单词已存在', 'word_id': existing.id}, status=409)

        # 自动获取或创建单元
        unit_number = int(data.get('unit_number', 99) or 99)
        unit, _ = Unit.objects.get_or_create(
            number=unit_number,
            defaults={
                'name': data.get('unit_name') or f'自定义 List {unit_number}',
                'category': data.get('category', 'required'),
            }
        )

        word = Word.objects.create(
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
            category=data.get('category', 'required'),
            unit=unit,
            list_number=unit.words.count() + 1,
        )

        # 更新单元词数
        unit.word_count = unit.words.count()
        unit.save()

        # 导入后自动 AI 补全（按词性释义 + 例句），失败不影响导入结果
        try:
            ai_complete_words([word])
        except Exception:
            pass

        return JsonResponse({'success': True, 'word_id': word.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_word_bulk_import(request):
    """批量导入单词 - AI识别结果批量导入（统一走规范化层）"""
    try:
        data = json.loads(request.body)
        words_data = data.get('words', [])
        if not words_data:
            return JsonResponse({'error': '没有单词数据'}, status=400)

        imported = 0
        skipped = 0
        imported_words = []
        new_word_objs = []
        unit_number = int(data.get('unit_number', 99) or 99)
        unit, _ = Unit.objects.get_or_create(
            number=unit_number,
            defaults={
                'name': data.get('unit_name') or f'自定义 List {unit_number}',
                'category': data.get('category', 'required'),
            }
        )

        next_list_number = (unit.words.aggregate(m=Max('list_number'))['m'] or 0) + 1

        # 批量预取已存在单词（小写集合），避免逐词 N+1 查询
        existing_lower = {w.lower() for w in Word.objects.values_list('word', flat=True)}

        for wd in words_data:
            nd = normalize_word_data(wd)
            if not nd:
                continue
            if nd['word'].lower() in existing_lower:
                skipped += 1
                continue
            existing_lower.add(nd['word'].lower())

            word = Word.objects.create(
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
                category=nd.get('category') or data.get('category', 'required'),
                unit=unit,
                list_number=next_list_number,
            )
            next_list_number += 1
            imported += 1
            imported_words.append(nd['word'])
            new_word_objs.append(word)

        unit.word_count = unit.words.count()
        unit.save()

        # 写入导入记录
        ImportLog.objects.create(
            source=data.get('source', 'text'),
            unit_number=unit_number,
            unit_name=unit.name,
            imported_count=imported,
            skipped_count=skipped,
            words_list=json.dumps(imported_words, ensure_ascii=False),
        )

        # 导入后自动 AI 补全（按词性释义 + 例句）改为后台异步执行：
        # 不让用户卡在导入按钮上，补全结果稍后自动出现在词库中；失败不影响导入结果。
        if new_word_objs:
            def _async_complete(objs):
                close_old_connections()
                try:
                    ai_complete_words(objs)
                except Exception:
                    pass
                finally:
                    close_old_connections()
            threading.Thread(target=_async_complete, args=(new_word_objs,), daemon=True).start()

        return JsonResponse({
            'success': True,
            'imported': imported,
            'skipped': skipped,
            'completing': bool(new_word_objs),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def import_logs(request):
    """导入记录页面：查看历史导入记录"""
    logs = ImportLog.objects.all()[:100]
    total_imported = ImportLog.objects.aggregate(
        t=Sum('imported_count'))['t'] or 0
    total_logs = ImportLog.objects.count()
    return render(request, 'import_logs.html', {
        'logs': logs,
        'total_imported': total_imported,
        'total_logs': total_logs,
    })


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def api_import_log_delete(request, log_id):
    """删除一条导入记录（仅删除记录，不影响已导入的单词）"""
    log = get_object_or_404(ImportLog, id=log_id)
    log.delete()
    return JsonResponse({'success': True, 'message': '记录已删除'})


@csrf_exempt
@require_http_methods(['POST'])
def api_word_update(request, word_id):
    """更新单词信息（完整字段）"""
    try:
        data = json.loads(request.body)
        word = get_object_or_404(Word, id=word_id)

        word.word = data.get('word', word.word).strip()
        word.phonetic_us = data.get('phonetic_us', word.phonetic_us)
        word.phonetic_uk = data.get('phonetic_uk', word.phonetic_uk)
        word.pos = data.get('pos', word.pos)
        word.category = data.get('category', word.category)

        meanings = data.get('meanings')
        meanings_by_pos = data.get('meanings_by_pos')
        if meanings_by_pos is not None:
            # 前端词性标签结构：以按词性分组为准，同步生成 pos 与 meanings（三字段一致）
            nd = normalize_word_data({
                'word': word.word,
                'pos': data.get('pos', word.pos),
                'meanings_by_pos': meanings_by_pos,
            })
            word.meanings_by_pos = json.dumps(nd['meanings_by_pos'], ensure_ascii=False)
            word.meanings = json.dumps(nd['meanings'], ensure_ascii=False)
            if nd['pos']:
                word.pos = nd['pos']
        elif meanings is not None:
            # 旧方式：手动修改释义文本 → 识别词性前缀重建分组
            nd = normalize_word_data({
                'word': word.word,
                'pos': data.get('pos', word.pos),
                'meanings': meanings,
            })
            word.meanings = json.dumps(nd['meanings'], ensure_ascii=False)
            word.meanings_by_pos = json.dumps(nd['meanings_by_pos'], ensure_ascii=False)
            if nd['pos']:
                word.pos = nd['pos']

        uncommon_meanings = data.get('uncommon_meanings')
        if uncommon_meanings is not None:
            word.uncommon_meanings = json.dumps(uncommon_meanings, ensure_ascii=False)

        collocations = data.get('collocations')
        if collocations is not None:
            word.collocations = json.dumps(collocations, ensure_ascii=False)

        word_forms = data.get('word_forms')
        if word_forms is not None:
            word.word_forms = json.dumps(word_forms, ensure_ascii=False)

        word.example_en = data.get('example_en', word.example_en)
        word.example_zh = data.get('example_zh', word.example_zh)

        if 'list_number' in data and data['list_number']:
            word.list_number = int(data['list_number'])

        # 单元变更：移动到指定单元（缺省时保持原单元）
        unit_number = data.get('unit_number')
        if unit_number:
            unit, _ = Unit.objects.get_or_create(
                number=int(unit_number),
                defaults={
                    'name': data.get('unit_name') or f'自定义 List {unit_number}',
                    'category': word.category,
                }
            )
            word.unit = unit

        word.save()

        # 更新新旧单元的词数
        if unit_number:
            for u in Unit.objects.filter(id__in=[word.unit_id]):
                u.word_count = u.words.count()
                u.save()
        word.unit.word_count = word.unit.words.count()
        word.unit.save()

        return JsonResponse({'success': True, 'message': '单词已更新'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST', 'DELETE'])
def api_word_delete(request, word_id):
    """删除单词"""
    try:
        word = get_object_or_404(Word, id=word_id)
        word_text = word.word
        unit = word.unit
        word.delete()

        if unit:
            unit.word_count = unit.words.count()
            unit.save()

        return JsonResponse({
            'success': True,
            'message': f'已删除单词 "{word_text}"',
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ─── AI 图片识别导入 ─────────────────────────────────────────

def extract_json_array(content):
    """从 AI 输出中稳健提取 JSON 数组"""
    if not content:
        return []
    content = content.strip()
    # 去掉可能的代码块围栏
    if content.startswith('```'):
        content = re.sub(r'^```[a-zA-Z]*\n?', '', content)
        content = re.sub(r'```$', '', content).strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get('words'), list):
            return parsed['words']
        return []
    except (json.JSONDecodeError, TypeError):
        pass
    # 兜底：截取首个 [ 到最后一个 ]
    start = content.find('[')
    end = content.rfind(']')
    if start != -1 and end > start:
        try:
            return json.loads(content[start:end + 1])
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def normalize_phonetic(ph):
    """规范化音标：确保用 / 包裹，去除多余空白"""
    ph = (ph or '').strip()
    if not ph:
        return ''
    # 已有斜杠包裹的直接返回
    if ph.startswith('/') and ph.endswith('/') and len(ph) > 1:
        return ph
    # 去除首尾零散斜杠后重新包裹
    ph = ph.strip('/').strip()
    return '/' + ph + '/' if ph else ''


# ─── 词性标签：识别与分组 ──────────────────────────────────
UNCLASSIFIED_POS = '未分类'
KNOWN_POS_TAGS = {
    'v.', 'vi.', 'vt.', 'n.', 'adj.', 'adv.', 'prep.', 'pron.',
    'conj.', 'num.', 'art.', 'aux.', 'interj.', 'int.', 'abbr.',
    'phr.', 'modal.', 'det.', 'pro.',
}
POS_PREFIX_RE = re.compile(r'^([a-zA-Z]+\.)\s*(.*)$')


def split_meanings_by_pos(meanings):
    """把释义文本识别词性前缀，解析为按词性分组字典。

    例如 ['v. 产生', 'v. 生成', 'n. 一代', '生成'] →
    {'v.': ['产生', '生成'], 'n.': ['一代'], '未分类': ['生成']}
    """
    result = {}
    for m in meanings:
        mm = str(m).strip()
        if not mm:
            continue
        mo = POS_PREFIX_RE.match(mm)
        if mo and mo.group(1).lower() in KNOWN_POS_TAGS:
            key = mo.group(1).lower()
            text = mo.group(2).strip()
            if text:
                result.setdefault(key, []).append(text)
        else:
            result.setdefault(UNCLASSIFIED_POS, []).append(mm)
    return result


def normalize_word_data(w):
    """规范化单个单词数据（音标、字段清理），所有导入入口共用。

    核心规则：pos / meanings / meanings_by_pos 三字段自动同步——
    - 若传入了 meanings_by_pos（词性标签 → 释义），则自动推导 pos 与 meanings
    - 若未传 meanings_by_pos，则从 meanings 文本中识别词性前缀自动分组
    """
    if not isinstance(w, dict):
        return None
    word_text = str(w.get('word', '')).strip()
    if not word_text:
        return None
    phonetic_us = normalize_phonetic(w.get('phonetic_us', '') or w.get('phonetic', ''))
    phonetic_uk = normalize_phonetic(w.get('phonetic_uk', ''))
    # 英式音标缺失时用美式填充，避免导入后音标空白
    if not phonetic_uk and phonetic_us:
        phonetic_uk = phonetic_us

    def _str_list(v):
        if isinstance(v, str):
            return [s.strip() for s in v.replace('；', ';').split(';') if s.strip()]
        if isinstance(v, (list, tuple)):
            return [str(s).strip() for s in v if str(s).strip()]
        return []

    def _str_dict(v):
        if not isinstance(v, dict):
            return {}
        clean = {}
        for k, vals in v.items():
            if isinstance(vals, (list, tuple)):
                items = [str(x).strip() for x in vals if str(x).strip()]
                if items:
                    clean[str(k).strip()] = items
        return clean

    meanings = _str_list(w.get('meanings'))
    meanings_by_pos = _str_dict(w.get('meanings_by_pos'))
    pos = str(w.get('pos', '') or '').strip()

    # 未提供按词性分组时，尝试从释义文本中识别词性前缀
    if not meanings_by_pos:
        meanings_by_pos = split_meanings_by_pos(meanings)

    # 按词性分组生效时，同步生成 pos（标签串）与 meanings（合并释义）
    if meanings_by_pos:
        pos_keys = [k for k in meanings_by_pos if k != UNCLASSIFIED_POS]
        if pos_keys:
            pos = '/'.join(pos_keys)
        merged = []
        for k in meanings_by_pos:
            merged.extend(meanings_by_pos[k])
        if merged:
            meanings = merged

    return {
        'word': word_text,
        'phonetic_us': phonetic_us,
        'phonetic_uk': phonetic_uk,
        'pos': pos,
        'meanings': meanings,
        'meanings_by_pos': meanings_by_pos,
        'uncommon_meanings': _str_list(w.get('uncommon_meanings')),
        'collocations': _str_list(w.get('collocations')),
        'word_forms': _str_dict(w.get('word_forms')),
        'example_en': str(w.get('example_en', '') or '').strip(),
        'example_zh': str(w.get('example_zh', '') or '').strip(),
    }


def normalize_ai_words(words):
    """规范化 AI 识别结果（基于公共规范化函数）"""
    clean = []
    for w in words:
        nd = normalize_word_data(w)
        if nd:
            clean.append(nd)
    return clean


def _ai_chat_once(cfg, prompt, max_tokens=4000):
    """单次调用 AI（OpenAI 兼容），返回纯文本内容"""
    payload = {
        'model': cfg['model_id'],
        'temperature': 0.5,
        'max_tokens': max_tokens,
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
    return content


def _extract_json_object(content):
    """从 AI 响应中提取 JSON 对象（兼容 ```json 包裹）"""
    s = content.find('{')
    e = content.rfind('}')
    if s == -1 or e == -1 or e <= s:
        return {}
    try:
        return json.loads(content[s:e + 1])
    except Exception:
        return {}


def ai_complete_words(word_objs):
    """导入后自动 AI 补全：为缺按词性释义 / 例句的单词批量生成（失败静默，不影响导入结果）"""
    if not word_objs:
        return
    # 需要按词性归类的：没有按词性释义，或全部被归到「未分类」
    need_pos = [
        w for w in word_objs
        if not w.get_meanings_by_pos() or all(k == '未分类' for k in w.get_meanings_by_pos())
    ]
    need_ex = [w for w in word_objs if not w.example_en.strip()]
    if not need_pos and not need_ex:
        return
    settings_obj = UserSettings.get_settings()
    model_data = {}
    if settings_obj.recognize_model:
        model_data['model_id'] = settings_obj.recognize_model_id
    try:
        cfg = resolve_ai_model(model_data)
    except ValueError:
        return
    batch = 30

    def _word_line(w):
        return '%s | %s | %s' % (w.word, w.pos or '', '；'.join(w.get_meanings()))

    try:
        # 1) 补按词性释义
        for i in range(0, len(need_pos), batch):
            chunk = need_pos[i:i + batch]
            lines = [_word_line(w) for w in chunk]
            prompt = pos_grouping_prompt(lines)
            try:
                data = _extract_json_object(_ai_chat_once(cfg, prompt))
            except Exception:
                data = {}
            for w in chunk:
                item = data.get(w.word)
                if isinstance(item, dict) and item:
                    w.meanings_by_pos = json.dumps(item, ensure_ascii=False)
                    w.save(update_fields=['meanings_by_pos'])
            time.sleep(0.5)
        # 2) 补例句
        for i in range(0, len(need_ex), batch):
            chunk = need_ex[i:i + batch]
            lines = [_word_line(w) for w in chunk]
            prompt = examples_prompt(lines)
            try:
                data = _extract_json_object(_ai_chat_once(cfg, prompt))
            except Exception:
                data = {}
            for w in chunk:
                item = data.get(w.word)
                if isinstance(item, dict) and item.get('en'):
                    w.example_en = item['en'].strip()
                    w.example_zh = (item.get('zh') or '').strip()
                    w.save(update_fields=['example_en', 'example_zh'])
            time.sleep(0.5)
    except Exception:
        pass


def resolve_ai_endpoint(base_url, endpoint):
    """拼接 OpenAI 兼容请求地址；endpoint 为完整 URL 时优先使用"""
    if endpoint and endpoint.strip():
        return endpoint.strip()
    return base_url.rstrip('/') + '/chat/completions'


def build_ai_headers(api_key):
    """构造请求头；无密钥时省略 Authorization（本机无鉴权服务如 opencode）。
    部分中转服务商（Codex2API 等）前端挂了 Cloudflare，会把 Python-urllib UA 拦成 502，
    这里统一填充浏览器 UA 以保证兼容性。"""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }
    if api_key and api_key.strip():
        headers['Authorization'] = 'Bearer ' + api_key.strip()
    return headers


def serialize_ai_model(m):
    """AIModel 数据库记录 → 前端 JSON"""
    return {
        'id': m.id,
        'provider': m.provider,
        'model_id': m.model_id,
        'display_name': m.display_name,
        'base_url': m.base_url,
        'endpoint': m.endpoint,
        'api_key': m.api_key,
        'context': m.context,
        'vision': m.vision,
        'enabled': m.enabled,
    }


def resolve_ai_model(data):
    """解析 AI 调用所需的模型配置（配置统一存数据库 AIModel 表，由设置页管理）。
    优先级：前端指定 model_id（数据库模型）> 前端内联配置（旧版兼容）> 数据库第一个启用模型。
    未找到时抛 ValueError，由调用方转为 400 响应。
    """
    model_id = data.get('model_id')
    if model_id:
        try:
            m = AIModel.objects.get(id=int(model_id))
        except (AIModel.DoesNotExist, ValueError, TypeError):
            raise ValueError('指定的模型不存在，请到「设置 → AI 模型」中重新选择')
        if not m.enabled:
            raise ValueError('该模型已被禁用，请到「设置 → AI 模型」中启用')
        return serialize_ai_model(m)
    # 旧版兼容：前端直接传 api_key/base_url/endpoint/model
    if data.get('model') or data.get('api_key') or data.get('base_url') or data.get('endpoint'):
        cfg = {
            'id': None,
            'provider': 'custom',
            'model_id': (data.get('model') or '').strip(),
            'display_name': data.get('model') or '',
            'base_url': (data.get('base_url') or 'https://api.openai.com/v1').strip(),
            'endpoint': (data.get('endpoint') or '').strip(),
            'api_key': (data.get('api_key') or '').strip(),
            'context': '128K',
            'vision': True,
            'enabled': True,
        }
        if not cfg['model_id']:
            raise ValueError('请填写模型 ID')
        return cfg
    m = AIModel.objects.filter(enabled=True).order_by('id').first()
    if not m:
        raise ValueError('尚未配置 AI 模型，请先到「设置 → AI 模型」中添加并启用一个模型')
    return serialize_ai_model(m)


@csrf_exempt
@require_http_methods(['GET', 'POST', 'DELETE'])
def api_ai_models(request):
    """AI 模型管理：GET 列表 / POST 新增或更新 / DELETE 删除（配置统一存数据库，设置页管理）"""
    if request.method == 'GET':
        models = AIModel.objects.all().order_by('-enabled', 'id')
        return JsonResponse({'models': [serialize_ai_model(m) for m in models]})

    if request.method == 'DELETE':
        try:
            body = json.loads(request.body)
        except Exception:
            body = {}
        mid = body.get('id') or request.GET.get('id')
        if mid:
            try:
                AIModel.objects.filter(id=int(mid)).delete()
            except (ValueError, TypeError):
                pass
        return JsonResponse({'success': True, 'deleted': mid})

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '请求格式错误'}, status=400)

    mid = data.get('id')
    if mid:
        try:
            m = AIModel.objects.get(id=int(mid))
        except (AIModel.DoesNotExist, ValueError, TypeError):
            return JsonResponse({'error': '模型不存在'}, status=404)
    else:
        m = AIModel()

    m.provider = (data.get('provider') or 'custom').strip() or 'custom'
    m.model_id = (data.get('model_id') or '').strip()
    m.display_name = (data.get('display_name') or '').strip()
    m.base_url = (data.get('base_url') or 'https://api.openai.com/v1').strip()
    m.endpoint = (data.get('endpoint') or '').strip()
    m.api_key = (data.get('api_key') or '').strip()
    m.context = (data.get('context') or '128K').strip() or '128K'
    if 'vision' in data:
        m.vision = bool(data.get('vision'))
    if 'enabled' in data:
        m.enabled = bool(data.get('enabled'))
    if not m.model_id:
        return JsonResponse({'error': '请填写模型 ID'}, status=400)
    m.save()
    return JsonResponse({'success': True, 'model': serialize_ai_model(m)})


@csrf_exempt
@require_http_methods(['POST'])
def api_ai_recognize(request):
    """AI 识别单词 → 结构化数据（OpenAI 兼容接口）
    支持三种输入源：图片(image) / 纯文本(text_content) / 文本文件(file_content)
    """
    try:
        data = json.loads(request.body)
        image_b64 = data.get('image', '')
        text_content = data.get('text_content', '')
        file_content = data.get('file_content', '')
        file_name = data.get('file_name', '')

        settings_obj = UserSettings.get_settings()
        if settings_obj.recognize_model and not data.get('model_id'):
            data['model_id'] = settings_obj.recognize_model_id

        try:
            cfg = resolve_ai_model(data)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        api_key = cfg['api_key']
        base_url = cfg['base_url']
        endpoint = cfg['endpoint']
        model = cfg['model_id']

        if image_b64:
            prompt = recognize_image_prompt()
            payload = {
                'model': model,
                'temperature': 0.1,
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {
                            'url': 'data:image/jpeg;base64,' + image_b64
                        }},
                    ],
                }],
            }
        elif text_content:
            if len(text_content) > 30000:
                return JsonResponse({'error': '文本过长，请控制在 30000 字符以内'}, status=400)
            prompt = recognize_text_prompt(text_content)
            payload = {
                'model': model,
                'temperature': 0.1,
                'messages': [{'role': 'user', 'content': prompt}],
            }
        elif file_content:
            if len(file_content) > 60000:
                return JsonResponse({'error': '文件内容过长，请控制在 60000 字符以内'}, status=400)
            prompt = recognize_file_prompt(file_name, file_content)
            payload = {
                'model': model,
                'temperature': 0.1,
                'messages': [{'role': 'user', 'content': prompt}],
            }
        else:
            return JsonResponse({'error': '请上传图片、粘贴文本或上传文件'}, status=400)

        req = urllib.request.Request(
            resolve_ai_endpoint(base_url, endpoint),
            data=json.dumps(payload).encode('utf-8'),
            headers=build_ai_headers(api_key),
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'ignore')
            return JsonResponse({'error': 'AI 接口错误 (HTTP %s): %s' % (e.code, body[:400])}, status=502)
        except urllib.error.URLError as e:
            url = resolve_ai_endpoint(base_url, endpoint)
            return JsonResponse({'error': '无法连接 %s: %s' % (url, e.reason)}, status=502)

        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        words = normalize_ai_words(extract_json_array(content))
        if not words:
            return JsonResponse({'error': 'AI 未能识别出有效单词，请检查输入内容或更换模型'}, status=422)

        return JsonResponse({'words': words, 'count': len(words)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def api_ai_review(request):
    """AI 复审：对识别结果进行二次校验，返回问题与修正建议"""
    try:
        data = json.loads(request.body)
        words = data.get('words', [])

        settings_obj = UserSettings.get_settings()
        if settings_obj.review_model and not data.get('model_id'):
            data['model_id'] = settings_obj.review_model_id

        try:
            cfg = resolve_ai_model(data)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        api_key = cfg['api_key']
        base_url = cfg['base_url']
        endpoint = cfg['endpoint']
        model = cfg['model_id']

        if not words:
            return JsonResponse({'error': '没有可复审的单词'}, status=400)

        words_json = json.dumps(words, ensure_ascii=False)
        prompt = ai_review_prompt(words_json)

        payload = {
            'model': model,
            'temperature': 0.1,
            'messages': [{'role': 'user', 'content': prompt}],
        }

        req = urllib.request.Request(
            resolve_ai_endpoint(base_url, endpoint),
            data=json.dumps(payload).encode('utf-8'),
            headers=build_ai_headers(api_key),
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'ignore')
            return JsonResponse({'error': 'AI 接口错误 (HTTP %s): %s' % (e.code, body[:400])}, status=502)
        except urllib.error.URLError as e:
            url = resolve_ai_endpoint(base_url, endpoint)
            return JsonResponse({'error': '无法连接 %s: %s' % (url, e.reason)}, status=502)

        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        review = extract_json_array(content)

        # 规范化：保证数量与输入一致，缺失项按"正确"处理
        normalized = []
        for i, w in enumerate(words):
            item = review[i] if i < len(review) and isinstance(review[i], dict) else {}
            norm = {
                'word': str(w.get('word', '')),
                'correct': bool(item.get('correct', True)),
                'issues': [str(x) for x in (item.get('issues') or []) if str(x).strip()],
            }
            suggested = item.get('suggested')
            if suggested:
                norm['suggested'] = str(suggested)
            fix = item.get('fix')
            if isinstance(fix, dict):
                clean_fix = {}
                if fix.get('word') and str(fix.get('word')).strip() != str(w.get('word', '')):
                    clean_fix['word'] = str(fix['word']).strip()
                if fix.get('pos') and str(fix.get('pos')).strip() != str(w.get('pos', '')):
                    clean_fix['pos'] = str(fix['pos']).strip()
                if fix.get('meanings') and isinstance(fix['meanings'], list):
                    m = [str(x).strip() for x in fix['meanings'] if str(x).strip()]
                    if m:
                        clean_fix['meanings'] = m
                if fix.get('phonetic_us'):
                    clean_fix['phonetic_us'] = normalize_phonetic(fix['phonetic_us'])
                if fix.get('phonetic_uk'):
                    clean_fix['phonetic_uk'] = normalize_phonetic(fix['phonetic_uk'])
                if fix.get('example_en'):
                    clean_fix['example_en'] = str(fix['example_en']).strip()
                if fix.get('example_zh'):
                    clean_fix['example_zh'] = str(fix['example_zh']).strip()
                if clean_fix:
                    norm['fix'] = clean_fix
            normalized.append(norm)

        issue_count = sum(1 for r in normalized if not r['correct'])
        return JsonResponse({'review': normalized, 'issues': issue_count, 'total': len(normalized)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(['POST'])
def api_ai_export_pdf(request):
    """人工审核导出 PDF：将 AI 识别结果导出为可离线核对的 PDF 清单"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': '请求格式错误'}, status=400)
    words = data.get('words') or []
    if not words:
        return JsonResponse({'error': '没有可导出的单词'}, status=400)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            leftMargin=15 * mm, rightMargin=15 * mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('title', fontName='STSong-Light', fontSize=14,
                                 leading=20, spaceAfter=4, alignment=1)
    sub_style = ParagraphStyle('sub', fontName='STSong-Light', fontSize=9,
                               leading=13, textColor=colors.grey, alignment=1)

    elements = [Paragraph('人工审核清单', title_style),
                Paragraph('共 %d 词 · 请离线核对打勾，完成后回到系统逐条确认' % len(words), sub_style),
                Spacer(1, 6 * mm)]

    table_data = [['序号', '单词', '音标', '词性', '释义', '状态']]
    for i, w in enumerate(words, 1):
        if not isinstance(w, dict):
            continue
        meanings_raw = w.get('meanings') or []
        if not isinstance(meanings_raw, list):
            meanings_raw = [meanings_raw]
        meanings_str = '; '.join([str(m) for m in meanings_raw if str(m).strip()])
        status = '待复核'
        if w.get('humanChecked'):
            status = '人工已核对'
        elif w.get('aiIssue'):
            status = 'AI 已修正'
        elif w.get('aiChecked'):
            status = 'AI 通过'
        table_data.append([
            str(i),
            str(w.get('word') or ''),
            str(w.get('phonetic_us') or w.get('phonetic_uk') or ''),
            str(w.get('pos') or ''),
            meanings_str,
            status,
        ])

    col_widths = [12 * mm, 42 * mm, 40 * mm, 14 * mm, 63 * mm, 24 * mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'STSong-Light'),
        ('FONTNAME', (0, 0), (0, -1), 'STSong-Light'),
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),
        ('FONTNAME', (2, 1), (2, -1), 'Helvetica'),
        ('FONTNAME', (3, 0), (3, -1), 'STSong-Light'),
        ('FONTNAME', (4, 0), (4, -1), 'STSong-Light'),
        ('FONTNAME', (5, 0), (5, -1), 'STSong-Light'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)

    doc.build(elements)
    buf.seek(0)
    return FileResponse(buf, content_type='application/pdf',
                        filename='人工审核_%s.pdf' % timezone.localdate().strftime('%Y%m%d'),
                        as_attachment=True)


@csrf_exempt
@require_http_methods(['POST'])
def api_ai_test(request):
    """测试 API 密钥与模型连通性（发送最小请求验证）"""
    try:
        data = json.loads(request.body)
        api_key = data.get('api_key', '')
        base_url = data.get('base_url', 'https://api.openai.com/v1')
        endpoint = data.get('endpoint', '')
        model = data.get('model', 'gpt-4o-mini')

        if not model:
            return JsonResponse({'error': '请填写模型 ID'}, status=400)

        payload = {
            'model': model,
            'max_tokens': 1,
            'messages': [{'role': 'user', 'content': 'ping'}],
        }

        req = urllib.request.Request(
            resolve_ai_endpoint(base_url, endpoint),
            data=json.dumps(payload).encode('utf-8'),
            headers=build_ai_headers(api_key),
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', 'ignore')
            # 401/403 = 密钥无效；404 = 模型或地址错误；其余透出
            return JsonResponse({
                'error': '连接失败 (HTTP %s): %s' % (e.code, body[:200]),
                'key_invalid': e.code in (401, 403),
                'model_invalid': e.code == 404,
            }, status=502)
        except urllib.error.URLError as e:
            url = resolve_ai_endpoint(base_url, endpoint)
            return JsonResponse({'error': '无法连接 %s: %s' % (url, e.reason)}, status=502)

        if result.get('choices'):
            return JsonResponse({'success': True, 'message': '连接成功，密钥有效'})
        return JsonResponse({'error': '接口响应异常'}, status=502)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
