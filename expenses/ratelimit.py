"""
Basit IP tabanlı rate limiter.
Django'nun cache backend'ini kullanır — ekstra bağımlılık yok.
"""
from django.core.cache import cache
from django.http import JsonResponse
from functools import wraps


def get_client_ip(request):
    """Gerçek client IP'sini döndürür (proxy arkasında da çalışır)."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def is_rate_limited(key, max_attempts, window_seconds):
    """
    Belirtilen key için rate limit kontrolü yapar.
    Dönüş: (limited: bool, attempts: int)
    """
    attempts = cache.get(key, 0)
    if attempts >= max_attempts:
        return True, attempts
    cache.set(key, attempts + 1, timeout=window_seconds)
    return False, attempts + 1


def rate_limit(max_attempts=5, window_seconds=300, key_prefix='rl'):
    """
    View decorator — IP başına max_attempts istek/window_seconds.
    Aşılırsa 429 döner.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method == 'POST':
                ip = get_client_ip(request)
                cache_key = f'{key_prefix}:{ip}'
                limited, attempts = is_rate_limited(
                    cache_key, max_attempts, window_seconds
                )
                if limited:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(
                            {'error': 'Çok fazla deneme. Lütfen bekleyin.'},
                            status=429
                        )
                    from django.contrib import messages
                    from django.shortcuts import redirect
                    messages.error(
                        request,
                        f'Çok fazla başarısız deneme. {window_seconds // 60} dakika bekleyin.'
                    )
                    response = redirect(request.path)
                    response.status_code = 429
                    return response
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


class RateLimitMixin:
    """
    Class-based view'lar için rate limit mixin'i.
    max_attempts ve window_seconds sınıf değişkenleriyle ayarlanır.
    """
    rate_limit_attempts = 10
    rate_limit_window = 300
    rate_limit_prefix = 'rl_cbv'

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'POST':
            ip = get_client_ip(request)
            cache_key = f'{self.rate_limit_prefix}:{self.__class__.__name__}:{ip}'
            limited, _ = is_rate_limited(
                cache_key,
                self.rate_limit_attempts,
                self.rate_limit_window
            )
            if limited:
                from django.contrib import messages
                from django.shortcuts import redirect
                messages.error(
                    request,
                    f'Çok fazla deneme. {self.rate_limit_window // 60} dakika bekleyin.'
                )
                response = redirect(request.path)
                response.status_code = 429
                return response
        return super().dispatch(request, *args, **kwargs)