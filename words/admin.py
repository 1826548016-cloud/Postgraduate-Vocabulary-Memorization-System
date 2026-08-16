from django.contrib import admin
from .models import (Unit, Word, StudyProgress, StudyPlan,
                     DailyCheckIn, Favorite, Note, StudySession, UserSettings, AIModel, StudyRecord)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ['number', 'name', 'category', 'word_count']
    list_filter = ['category']


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ['word', 'pos', 'category', 'unit', 'list_number']
    list_filter = ['category', 'unit']
    search_fields = ['word', 'meanings']


@admin.register(StudyProgress)
class StudyProgressAdmin(admin.ModelAdmin):
    list_display = ['word', 'status', 'mastery_level', 'review_count',
                    'error_count', 'next_review']
    list_filter = ['status', 'mastery_level']


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'daily_new_words', 'daily_review_count',
                    'is_active', 'target_date']


@admin.register(DailyCheckIn)
class DailyCheckInAdmin(admin.ModelAdmin):
    list_display = ['date', 'new_words_learned', 'words_reviewed',
                    'study_duration', 'correct_rate', 'is_checked']


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ['word', 'created_at']


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ['word', 'page_number', 'updated_at']


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ['date', 'mode', 'words_count', 'correct_count']


@admin.register(StudyRecord)
class StudyRecordAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'word', 'action', 'source', 'mode']
    list_filter = ['source', 'action']
    search_fields = ['word__word']
    date_hierarchy = 'created_at'


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ['font_size', 'dark_mode', 'pronunciation_on',
                    'speech_rate', 'daily_new_target']


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'model_id', 'provider', 'vision',
                    'enabled', 'updated_at']
    list_filter = ['provider', 'enabled', 'vision']
    search_fields = ['model_id', 'display_name']
