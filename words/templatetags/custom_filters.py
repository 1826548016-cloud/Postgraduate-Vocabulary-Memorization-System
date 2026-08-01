import json
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """获取字典中的值"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''


@register.filter
def json_loads(value):
    """将 JSON 字符串转为 Python 对象"""
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []


@register.filter
def status_badge_class(status):
    """返回状态对应的 badge CSS 类名"""
    mapping = {
        'new': 'badge-new',
        'learning': 'badge-learning',
        'reviewing': 'badge-reviewing',
        'mastered': 'badge-mastered',
    }
    return mapping.get(status, 'badge-new')


@register.filter
def status_display(status):
    """返回状态中文名"""
    mapping = {
        'new': '未学',
        'learning': '学习中',
        'reviewing': '复习中',
        'mastered': '已掌握',
    }
    return mapping.get(status, status)


@register.filter
def category_display(code):
    """返回类别中文名"""
    mapping = {
        'required': '必考词',
        'basic': '基础词',
        'advanced': '超纲词',
    }
    return mapping.get(code, code)


@register.filter
def dict_get(d, key):
    """从字典中获取值"""
    try:
        return d.get(key)
    except (AttributeError, TypeError):
        return ''
