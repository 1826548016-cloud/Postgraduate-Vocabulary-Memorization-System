import json
import os
import random
import re
import shutil
import urllib.request
import urllib.error
from datetime import date, timedelta, datetime
from io import BytesIO

from django.conf import settings
from django.db.models import Q, Count, Sum, Avg, F
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (Unit, Word, StudyProgress, StudyPlan,
                     DailyCheckIn, Favorite, Note, QuickMemory, AIModel, StudySession, UserSettings, ChatMessage, ImportLog)

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

    context = {
        'today_new': today_new,
        'today_review': today_review,
        'review_due': review_due,
        'settings': settings_obj,
        'plan': active_plan,
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
    return render(request, 'learn_start.html', {'units': units})


def learn_session(request):
    mode = request.GET.get('mode', 'sequential')
    unit_ids = request.GET.getlist('units')
    scope = request.GET.get('scope', 'unknown')

    query = Word.objects.all()
    if unit_ids:
        query = query.filter(unit__number__in=unit_ids)

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

    word_data = []
    for w in words:
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
        })

    # 用 session 记录词 ID 列表（供复习页用）
    request.session['learn_words'] = [w['id'] for w in word_data]
    request.session['learn_mode'] = mode

    return render(request, 'learn_session.html', {
        'word_count': len(word_data),
        'mode': mode,
        'words_json': json.dumps(word_data, ensure_ascii=False),
    })


def review_session(request):
    """复习：从所有已学词汇中随机抽取，不再使用艾宾浩斯曲线。"""
    today = timezone.localdate()
    settings_obj = UserSettings.get_settings()
    target = max(1, settings_obj.daily_review_target)

    # 从所有已学词（status 不为 'new'）中随机抽取
    all_progress = list(StudyProgress.objects.exclude(status='new').select_related('word'))
    random.shuffle(all_progress)
    batch = all_progress[:target]

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
        })

    mastered_count = len([p for p in batch if p.status == 'mastered'])
    unmastered_count = len(batch) - mastered_count

    return render(request, 'review_session.html', {
        'review_count': len(word_data),
        'words_json': json.dumps(word_data, ensure_ascii=False),
        'total_due': len(all_progress),  # 总已学词数
        'remaining_due': max(0, len(all_progress) - len(word_data)),
        'daily_review_target': settings_obj.daily_review_target,
        'batch_date': today.isoformat(),
        'unmastered_in_batch': unmastered_count,
        'mastered_in_batch': mastered_count,
    })


def statistics(request):
    return render(request, 'stats.html')


def exam(request):
    """模拟考试：配置页"""
    units = Unit.objects.all()
    return render(request, 'exam.html', {'units': units})


def study_plan(request):
    plans = StudyPlan.objects.all().order_by('-is_active', '-created_at')
    return render(request, 'plan.html', {'plans': plans})


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
            'is_favorite': has_fav,
        })

    return JsonResponse({'words': words_data, 'total': total, 'page': page})


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

    # 今日需复习：从所有已学词中随机抽取
    all_progress = list(StudyProgress.objects.exclude(status='new').select_related('word'))
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

    title_style = ParagraphStyle('title', fontName='STSong-Light', fontSize=14,
                                 leading=20, spaceAfter=10, alignment=1)

    elements = [Paragraph(title_text, title_style),
                Spacer(1, 6 * mm)]

    total_rows = len(words)
    table_data = []
    # Header (no phonetic to avoid garbled text)
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
        col_widths = [14 * mm, 44 * mm, 18 * mm, 79 * mm]
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'STSong-Light'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),
            ('FONTNAME', (0, 0), (0, -1), 'STSong-Light'),
            ('FONTNAME', (3, 0), (3, -1), 'STSong-Light'),
            ('FONTNAME', (4, 0), (4, -1), 'STSong-Light'),
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
@require_http_methods(['POST'])
def api_settings(request):
    try:
        data = json.loads(request.body)
        settings_obj = UserSettings.get_settings()
        for k, v in data.items():
            if hasattr(settings_obj, k):
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

    prompt = (
        f'你是一名英语词汇记忆专家，擅长用拆分、谐音、联想口诀帮考研学生速记单词。\n'
        f'请为单词 "{word_text}" 创作一份速记内容，格式严格如下（不要输出任何多余文字）：\n\n'
        f'{word_text} 速记\n'
        f'英 /{phonetic_uk}/ 美 /{phonetic_us}/\n'
        f'{pos} {meanings}\n'
        f'拆分秒背（最好用）\n'
        f'拆成N段：seg1 + seg2 + ...\n'
        f'谐音：中文谐音\n'
        f'联想口诀：用各部分谐音/含义串成一句生动小故事\n\n'
        f'要求：\n'
        f'- 按音节自然拆分（如 environment → en + vi + ron + ment），N 用实际段数替换\n'
        f'- 谐音要贴近英文发音\n'
        f'- 口诀把每段的中文谐音或含义串成一句话，控制在 2 句以内\n'
        f'- 若单词很短（3 个字母以内）可不拆分，直接编口诀\n'
        f'- 音标若已有则保留，未提供可省略对应行'
    )

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
    system_prompt = (
        '你是「考研单词」学习 App 中的英语学习小助手，用户在背单词时向你提问。\n'
        '要求：\n'
        '- 用中文回答，准确、简洁、有条理\n'
        '- 可讲解单词考法：词义辨析、固定搭配、词形变化、真题/考试常见考法、记忆技巧等\n'
        '- 结合上下文保持对话连贯；不确定的内容要如实说明\n'
        '- 排版要求：用清晰的 Markdown 格式组织回答——用 ### 小标题分节、**加粗** 关键词、\n'
        '  用 - 或 1. 列表、用 --- 分隔线、善用表格，让答案层次分明、便于阅读\n'
    )
    messages = [{'role': 'system', 'content': system_prompt}]

    if word:
        word_ctx = (
            f'当前单词：{word.word}\n'
            f'音标：英 /{word.phonetic_uk or "-"}/ 美 /{word.phonetic_us or "-"}/\n'
            f'词性：{word.pos or "-"}\n'
            f'释义：{"；".join(word.get_meanings()[:5]) or "-"}\n'
            f'搭配：{"；".join(word.get_collocations()[:5]) or "-"}\n'
            f'词形变化：{word.get_word_forms() or "-"}\n'
            f'例句：{word.example_en or ""} {word.example_zh or ""}'
        )
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

    word_data = []
    for w in words:
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
        })

    # 存入 session 供交卷时评分
    request.session['exam_direction'] = direction
    request.session['exam_questions'] = [
        {'id': q['id'], 'options': q['options'], 'correct_index': q['correct_index']}
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

        answer_map = {a['word_id']: a.get('selected') for a in answers}

        today = timezone.localdate()
        now = timezone.now()
        checkin, _ = DailyCheckIn.objects.get_or_create(date=today)

        results = []
        correct_count = 0
        for sq in stored:
            qid = sq['id']
            correct_index = sq['correct_index']
            selected = answer_map.get(qid)
            is_correct = (selected == correct_index)
            if is_correct:
                correct_count += 1

            word = Word.objects.filter(id=qid).first()
            if word:
                progress, _ = StudyProgress.objects.get_or_create(word=word)
                if progress.status == 'new':
                    progress.learned_date = today
                    progress.is_today_new = True
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
                    'selected_index': selected,
                    'correct_index': correct_index,
                })
            else:
                results.append({
                    'word_id': qid, 'word': '?', 'meanings': [],
                    'correct': is_correct, 'selected_index': selected,
                    'correct_index': correct_index,
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
    """手动添加或 AI 导入单词"""
    try:
        data = json.loads(request.body)
        word_text = data.get('word', '').strip()
        if not word_text:
            return JsonResponse({'error': '单词不能为空'}, status=400)

        # 如果单词已存在，返回已存在信息
        existing = Word.objects.filter(word__iexact=word_text).first()
        if existing:
            return JsonResponse({'error': '单词已存在', 'word_id': existing.id}, status=409)

        # 自动获取或创建单元
        unit_number = data.get('unit_number', 99)
        unit, _ = Unit.objects.get_or_create(
            number=unit_number,
            defaults={
                'name': data.get('unit_name') or f'自定义 List {unit_number}',
                'category': data.get('category', 'required'),
            }
        )

        word = Word.objects.create(
            word=word_text,
            phonetic_us=data.get('phonetic_us', ''),
            phonetic_uk=data.get('phonetic_uk', ''),
            pos=data.get('pos', ''),
            meanings=json.dumps(data.get('meanings', []), ensure_ascii=False),
            uncommon_meanings=json.dumps(data.get('uncommon_meanings', []), ensure_ascii=False),
            collocations=json.dumps(data.get('collocations', []), ensure_ascii=False),
            word_forms=json.dumps(data.get('word_forms', {}), ensure_ascii=False),
            example_en=data.get('example_en', ''),
            example_zh=data.get('example_zh', ''),
            category=data.get('category', 'required'),
            unit=unit,
            list_number=data.get('list_number', 1),
        )

        # 更新单元词数
        unit.word_count = unit.words.count()
        unit.save()

        return JsonResponse({'success': True, 'word_id': word.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def api_word_bulk_import(request):
    """批量导入单词 - AI识别结果批量导入"""
    try:
        data = json.loads(request.body)
        words_data = data.get('words', [])
        if not words_data:
            return JsonResponse({'error': '没有单词数据'}, status=400)

        imported = 0
        skipped = 0
        imported_words = []
        unit_number = data.get('unit_number', 99)
        unit, _ = Unit.objects.get_or_create(
            number=unit_number,
            defaults={
                'name': data.get('unit_name') or f'自定义 List {unit_number}',
                'category': data.get('category', 'required'),
            }
        )

        for wd in words_data:
            word_text = wd.get('word', '').strip()
            if not word_text:
                continue
            if Word.objects.filter(word__iexact=word_text).exists():
                skipped += 1
                continue

            Word.objects.create(
                word=word_text,
                phonetic_us=wd.get('phonetic_us', ''),
                phonetic_uk=wd.get('phonetic_uk', ''),
                pos=wd.get('pos', ''),
                meanings=json.dumps(wd.get('meanings', []), ensure_ascii=False),
                uncommon_meanings=json.dumps(wd.get('uncommon_meanings', []), ensure_ascii=False),
                collocations=json.dumps(wd.get('collocations', []), ensure_ascii=False),
                word_forms=json.dumps(wd.get('word_forms', {}), ensure_ascii=False),
                example_en=wd.get('example_en', ''),
                example_zh=wd.get('example_zh', ''),
                category=wd.get('category', 'required'),
                unit=unit,
                list_number=wd.get('list_number', imported + 1),
            )
            imported += 1
            imported_words.append(word_text)

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

        return JsonResponse({
            'success': True,
            'imported': imported,
            'skipped': skipped,
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
        if meanings is not None:
            word.meanings = json.dumps(meanings, ensure_ascii=False)
            # 释义被手动修改后，旧的按词性分组不再可靠，清空以回退到普通展示
            word.meanings_by_pos = '{}'

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


def normalize_ai_words(words):
    """规范化 AI 识别结果"""
    clean = []
    for w in words:
        if not isinstance(w, dict):
            continue
        word_text = str(w.get('word', '')).strip()
        if not word_text:
            continue
        phonetic_us = normalize_phonetic(w.get('phonetic_us', '') or w.get('phonetic', ''))
        phonetic_uk = normalize_phonetic(w.get('phonetic_uk', ''))
        # 英式音标缺失时用美式填充，避免导入后音标空白
        if not phonetic_uk and phonetic_us:
            phonetic_uk = phonetic_us
        clean.append({
            'word': word_text,
            'phonetic_us': phonetic_us,
            'phonetic_uk': phonetic_uk,
            'pos': str(w.get('pos', '') or '').strip(),
            'meanings': [str(m).strip() for m in (w.get('meanings') or [])
                         if str(m).strip()],
            'example_en': str(w.get('example_en', '') or '').strip(),
            'example_zh': str(w.get('example_zh', '') or '').strip(),
        })
    return clean


def resolve_ai_endpoint(base_url, endpoint):
    """拼接 OpenAI 兼容请求地址；endpoint 为完整 URL 时优先使用"""
    if endpoint and endpoint.strip():
        return endpoint.strip()
    return base_url.rstrip('/') + '/chat/completions'


def build_ai_headers(api_key):
    """构造请求头；无密钥时省略 Authorization（本机无鉴权服务如 opencode）"""
    headers = {'Content-Type': 'application/json'}
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

        try:
            cfg = resolve_ai_model(data)
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        api_key = cfg['api_key']
        base_url = cfg['base_url']
        endpoint = cfg['endpoint']
        model = cfg['model_id']

        json_schema = (
            '[{"word": "单词拼写", "phonetic_us": "美式音标如/ˈdʒenəreɪt/", '
            '"phonetic_uk": "英式音标(可选)", "pos": "词性如v./n./adj.", '
            '"meanings": ["中文释义1", "中文释义2"], '
            '"example_en": "英文例句(可选)", "example_zh": "中文翻译(可选)"}]\n'
        )
        common_rules = (
            '要求：\n'
            '1. 完整整理所有出现的单词，不要遗漏任何一个\n'
            '2. 尽量给出每个单词的美式音标（phonetic_us），用 / 包裹，如 /əˈbændən/；'
            '若原文已标注音标则直接使用，若无法确定请根据单词拼写推断常见读音\n'
            '3. 释义使用中文，多个义项放入 meanings 数组\n'
            '4. 若包含词组/搭配，把短语作为单词输出\n'
            '5. 只输出 JSON 本身，不要输出任何多余文字、不要用代码块包裹'
        )

        if image_b64:
            prompt = (
                '你是一个专业的英语词汇整理助手。请识别图片中的所有英语单词，'
                '并严格按以下 JSON 数组格式输出：\n' + json_schema +
                '要求：\n'
                '1. 完整识别图中所有单词，不要遗漏任何一个\n'
                '2. 音标若无法准确识别可以留空\n'
                '3. 释义使用中文，多个义项放入 meanings 数组\n'
                '4. 按图片中从左到右、从上到下的顺序输出\n'
                '5. 若图片包含词组/搭配，把短语作为单词输出\n'
                '6. 只输出 JSON 本身'
            )
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
            prompt = (
                '你是一个专业的英语词汇整理助手。请从下面的文本中提取所有英语单词/词组'
                '（若文本本身是词表，则整理其中每一行），并严格按以下 JSON 数组格式输出：\n' + json_schema +
                common_rules + '\n\n文本内容如下：\n\n' + text_content
            )
            payload = {
                'model': model,
                'temperature': 0.1,
                'messages': [{'role': 'user', 'content': prompt}],
            }
        elif file_content:
            if len(file_content) > 60000:
                return JsonResponse({'error': '文件内容过长，请控制在 60000 字符以内'}, status=400)
            prompt = (
                '你是一个专业的英语词汇整理助手。请从文件「%s」的内容中提取所有英语单词/词组'
                '（若内容本身是词表，则整理其中每一行），并严格按以下 JSON 数组格式输出：\n' % (file_name or '未命名') + json_schema +
                common_rules + '\n\n文件内容如下：\n\n' + file_content
            )
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
        prompt = (
            '你是一个英语词汇质检专家。以下是 AI 从图片/文本中识别出的单词列表，'
            '请逐条校验拼写、词性、中文释义是否正确合理。\n'
            '输出要求：\n'
            '- 严格输出 JSON 数组，数组长度与输入单词数量一致，顺序一致，不要遗漏\n'
            '- 每项格式：{"word": "原单词", "correct": true/false, '
            '"issues": ["问题描述1", "问题描述2"], "suggested": "简短修改建议(可选)", '
            '"fix": {"word": "修正后单词(仅拼写错误时)", "pos": "修正后词性(仅错误时)", "meanings": ["修正后释义1"]}}\n'
            '- correct 为 true 时 issues 为空数组，fix 可为 null\n'
            '- 只输出 JSON 本身，不要输出任何多余文字、不要用代码块包裹\n\n'
            '待复审的单词列表：\n' + words_json
        )

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
