from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse


def vite_client_stub(request):
    # 占位：防止 /@vite/client 404 噪音
    return HttpResponse(
        "// Vite HMR client stub (not used)\nexport default {};\n",
        content_type="application/javascript",
    )

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('mbti.urls', 'mbti'), namespace='mbti')),
    path('users/', include(('users.urls', 'users'), namespace='users')),
    # 兼容处理前端或扩展误发起的 HMR 客户端请求
    path('@vite/client', vite_client_stub),
]