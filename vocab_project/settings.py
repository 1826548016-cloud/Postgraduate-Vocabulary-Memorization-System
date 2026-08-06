"""
Django settings for vocab_project project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# 桌面版打包后：程序资源目录与用户数据目录分离
# 开发时两者都是项目根目录，行为与原来一致
APP_DIR = Path(os.environ.get('VOCAB_APP_DIR', str(BASE_DIR)))
DATA_DIR = Path(os.environ.get('VOCAB_DATA_DIR', str(BASE_DIR)))

SECRET_KEY = 'django-insecure-%3#v_5wpj1rord)qcqs*s0v0@hfb-y#8=q6k=(oy7ho=4vdxk'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'words',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'vocab_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [APP_DIR / 'words' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'vocab_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DATA_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    APP_DIR / 'words' / 'static',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = DATA_DIR / 'media'

BACKUP_DIR = DATA_DIR / 'backups'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
