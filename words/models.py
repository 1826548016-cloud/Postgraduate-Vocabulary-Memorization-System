import json
from django.db import models
from django.utils import timezone


class Unit(models.Model):
    number = models.IntegerField(unique=True, verbose_name='单元编号')
    name = models.CharField(max_length=100, verbose_name='单元名称')
    category = models.CharField(max_length=20, verbose_name='词汇类别',
        choices=[('required', '必考词'), ('basic', '基础词'), ('advanced', '超纲词')])
    word_count = models.IntegerField(default=0, verbose_name='单词数量')

    class Meta:
        ordering = ['number']
        verbose_name = '单元'
        verbose_name_plural = '单元'

    def __str__(self):
        return f'List {self.number} - {self.name}'

    def mastered_count(self):
        return StudyProgress.objects.filter(
            word__unit=self, status='mastered'
        ).count()

    def progress_percent(self):
        if self.word_count == 0:
            return 0
        return round(self.mastered_count() / self.word_count * 100, 1)


class Word(models.Model):
    CATEGORY_CHOICES = [
        ('required', '必考词'),
        ('basic', '基础词'),
        ('advanced', '超纲词'),
    ]

    word = models.CharField(max_length=100, unique=True, verbose_name='单词')
    phonetic_us = models.CharField(max_length=100, blank=True, verbose_name='美式音标')
    phonetic_uk = models.CharField(max_length=100, blank=True, verbose_name='英式音标')
    pos = models.CharField(max_length=50, blank=True, verbose_name='词性')
    meanings = models.TextField(verbose_name='释义', default='[]',
        help_text='JSON格式: ["释义1", "释义2"]')
    uncommon_meanings = models.TextField(blank=True, verbose_name='熟词僻义',
        default='[]')
    collocations = models.TextField(blank=True, verbose_name='搭配',
        default='[]')
    word_forms = models.TextField(blank=True, verbose_name='词形变化',
        default='{}')
    example_en = models.TextField(blank=True, verbose_name='英文例句')
    example_zh = models.TextField(blank=True, verbose_name='中文翻译')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES,
        verbose_name='词汇类别', db_index=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE,
        related_name='words', verbose_name='所属单元')
    list_number = models.IntegerField(default=1, verbose_name='List内序号')

    class Meta:
        ordering = ['unit__number', 'list_number']
        verbose_name = '单词'
        verbose_name_plural = '单词'
        indexes = [
            models.Index(fields=['unit', 'list_number']),
            models.Index(fields=['category']),
        ]

    def __str__(self):
        return self.word

    def get_meanings(self):
        try:
            return json.loads(self.meanings)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_uncommon_meanings(self):
        try:
            return json.loads(self.uncommon_meanings)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_collocations(self):
        try:
            return json.loads(self.collocations)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_word_forms(self):
        try:
            return json.loads(self.word_forms)
        except (json.JSONDecodeError, TypeError):
            return {}

    def meanings_display(self):
        return '; '.join(self.get_meanings())


class StudyProgress(models.Model):
    STATUS_CHOICES = [
        ('new', '未学'),
        ('learning', '学习中'),
        ('reviewing', '复习中'),
        ('mastered', '已掌握'),
    ]

    word = models.OneToOneField(Word, on_delete=models.CASCADE,
        related_name='progress', verbose_name='单词')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
        default='new', verbose_name='状态', db_index=True)
    mastery_level = models.IntegerField(default=0, verbose_name='掌握等级', db_index=True)
    review_count = models.IntegerField(default=0, verbose_name='复习次数')
    error_count = models.IntegerField(default=0, verbose_name='错误次数')
    last_review = models.DateTimeField(null=True, blank=True,
        verbose_name='上次复习')
    next_review = models.DateField(null=True, blank=True,
        verbose_name='下次复习', db_index=True)
    is_today_new = models.BooleanField(default=False, verbose_name='今日新学')
    learned_date = models.DateField(null=True, blank=True,
        verbose_name='首次学习日期', db_index=True)
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '学习进度'
        verbose_name_plural = '学习进度'
        indexes = [
            models.Index(fields=['status', 'next_review']),
            models.Index(fields=['learned_date', 'is_today_new']),
        ]

    def __str__(self):
        return f'{self.word.word} - {self.status} (L{self.mastery_level})'


class StudyPlan(models.Model):
    name = models.CharField(max_length=100, verbose_name='计划名称')
    daily_new_words = models.IntegerField(default=30, verbose_name='每日新词数')
    daily_review_count = models.IntegerField(default=50, verbose_name='每日复习量')
    target_date = models.DateField(null=True, blank=True,
        verbose_name='目标完成日期')
    unit_range = models.TextField(default='[]', verbose_name='单元范围')
    is_active = models.BooleanField(default=False, verbose_name='是否激活')
    start_date = models.DateField(auto_now_add=True, verbose_name='开始日期')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = '学习计划'
        verbose_name_plural = '学习计划'

    def __str__(self):
        return self.name

    def get_unit_range(self):
        try:
            return json.loads(self.unit_range)
        except (json.JSONDecodeError, TypeError):
            return []

    def remaining_words(self):
        unit_nums = self.get_unit_range()
        if not unit_nums:
            total = Word.objects.count()
        else:
            total = Word.objects.filter(unit__number__in=unit_nums).count()
        learned = StudyProgress.objects.exclude(status='new').count()
        return max(0, total - learned)

    def estimated_days(self):
        remaining = self.remaining_words()
        if self.daily_new_words <= 0:
            return 0
        return (remaining + self.daily_new_words - 1) // self.daily_new_words


class DailyCheckIn(models.Model):
    date = models.DateField(unique=True, verbose_name='日期')
    new_words_learned = models.IntegerField(default=0, verbose_name='新学词数')
    words_reviewed = models.IntegerField(default=0, verbose_name='复习词数')
    study_duration = models.IntegerField(default=0, verbose_name='学习时长(秒)')
    correct_rate = models.FloatField(default=0, verbose_name='正确率')
    today_correct = models.IntegerField(default=0, verbose_name='今日正确数')
    today_wrong = models.IntegerField(default=0, verbose_name='今日错误数')
    is_checked = models.BooleanField(default=False, verbose_name='是否打卡')

    class Meta:
        ordering = ['-date']
        verbose_name = '每日打卡'
        verbose_name_plural = '每日打卡'

    def __str__(self):
        return f'{self.date} - 新{self.new_words_learned} 复习{self.words_reviewed}'


class Favorite(models.Model):
    word = models.OneToOneField(Word, on_delete=models.CASCADE,
        related_name='favorite', verbose_name='单词')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='收藏时间')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '收藏'
        verbose_name_plural = '收藏'

    def __str__(self):
        return self.word.word


class Note(models.Model):
    word = models.OneToOneField(Word, on_delete=models.CASCADE,
        related_name='note', verbose_name='单词')
    content = models.TextField(blank=True, verbose_name='笔记内容')
    page_number = models.IntegerField(null=True, blank=True,
        verbose_name='书页码')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '笔记'
        verbose_name_plural = '笔记'

    def __str__(self):
        return f'{self.word.word} - 笔记'


class QuickMemory(models.Model):
    """速记：AI 生成的单词快速记忆内容，缓存到数据库，下次直接读取不再调用 AI"""
    word = models.OneToOneField(Word, on_delete=models.CASCADE,
        related_name='quick_memory', verbose_name='单词')
    content = models.TextField(blank=True, verbose_name='速记内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '速记'
        verbose_name_plural = '速记'

    def __str__(self):
        return f'{self.word.word} - 速记'


class StudySession(models.Model):
    MODE_CHOICES = [
        ('sequential', '顺序背诵'),
        ('random', '乱序背诵'),
        ('cover_en', '遮英文'),
        ('cover_zh', '遮中文'),
        ('review', '复习'),
        ('favorite', '收藏复习'),
        ('exam', '模拟考试'),
    ]

    date = models.DateField(verbose_name='日期')
    mode = models.CharField(max_length=20, choices=MODE_CHOICES,
        verbose_name='学习模式')
    start_time = models.DateTimeField(auto_now_add=True, verbose_name='开始时间')
    end_time = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')
    words_count = models.IntegerField(default=0, verbose_name='单词数')
    correct_count = models.IntegerField(default=0, verbose_name='正确数')

    class Meta:
        ordering = ['-start_time']
        verbose_name = '学习会话'
        verbose_name_plural = '学习会话'

    @property
    def correct_rate(self):
        if self.words_count == 0:
            return 0
        return round(self.correct_count / self.words_count * 100, 1)


class UserSettings(models.Model):
    FONT_CHOICES = [
        ('small', '小'),
        ('medium', '中'),
        ('large', '大'),
    ]
    VOICE_CHOICES = [
        ('us', '美音'),
        ('uk', '英音'),
    ]

    font_size = models.CharField(max_length=10, choices=FONT_CHOICES,
        default='medium', verbose_name='字体大小')
    dark_mode = models.BooleanField(default=False, verbose_name='深色模式')
    pronunciation_on = models.BooleanField(default=True, verbose_name='发音开关')
    auto_read = models.BooleanField(default=True, verbose_name='自动朗读')
    speech_rate = models.FloatField(default=1.0, verbose_name='语速')
    voice_type = models.CharField(max_length=5, choices=VOICE_CHOICES,
        default='us', verbose_name='发音类型')
    daily_new_target = models.IntegerField(default=30, verbose_name='每日新词目标')
    daily_review_target = models.IntegerField(default=50, verbose_name='每日复习目标')
    assistant_model = models.ForeignKey('AIModel', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+', verbose_name='小助手模型')

    class Meta:
        verbose_name = '用户设置'
        verbose_name_plural = '用户设置'

    def __str__(self):
        return '用户设置'

    @classmethod
    def get_settings(cls):
        settings = cls.objects.first()
        if not settings:
            settings = cls.objects.create()
        return settings


class ChatMessage(models.Model):
    """小助手对话记录：背诵/专注/复习三个模式共用同一条对话，历史持久化保存"""
    ROLE_CHOICES = [
        ('user', '用户'),
        ('assistant', '小助手'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色')
    content = models.TextField(verbose_name='内容')
    word_id = models.IntegerField(null=True, blank=True, verbose_name='关联单词 ID')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        ordering = ['id']
        verbose_name = '小助手对话'
        verbose_name_plural = '小助手对话'

    def __str__(self):
        return f'{self.role}: {self.content[:30]}'


class AIModel(models.Model):
    """AI 模型配置：集中存储在数据库，由设置页统一管理"""
    provider = models.CharField(max_length=50, default='openai', verbose_name='服务商')
    model_id = models.CharField(max_length=100, verbose_name='模型 ID')
    display_name = models.CharField(max_length=100, blank=True, verbose_name='展示名称')
    base_url = models.CharField(max_length=300, default='https://api.openai.com/v1', verbose_name='接口基础地址')
    endpoint = models.CharField(max_length=400, blank=True, verbose_name='完整请求地址')
    api_key = models.CharField(max_length=300, blank=True, verbose_name='API 密钥')
    context = models.CharField(max_length=10, blank=True, default='128K', verbose_name='上下文')
    vision = models.BooleanField(default=True, verbose_name='支持图片识别')
    enabled = models.BooleanField(default=True, verbose_name='启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = 'AI 模型'
        verbose_name_plural = 'AI 模型'

    def __str__(self):
        return self.display_name or self.model_id
