from django.http import JsonResponse
from django.shortcuts import redirect

LOGIN_URL = '/login/'


class LoginRequiredMiddleware:
    """个人使用的简易登录校验：未登录时页面跳转登录页，API 请求返回 401。"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.session.get('is_logged_in'):
            path = request.path
            # 登录页和静态资源无需登录
            if path == LOGIN_URL or path.startswith('/static/'):
                return self.get_response(request)
            if path.startswith('/api/'):
                return JsonResponse({'error': '未登录'}, status=401)
            return redirect(LOGIN_URL + '?next=' + request.path)
        return self.get_response(request)
