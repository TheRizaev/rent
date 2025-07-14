from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('superuser/', include('rental.admin_urls')),
    path('', include('rental.urls')),
]

# ИСПРАВЛЕНО: Добавляем обслуживание медиа файлов как для DEBUG=True, так и для продакшена
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
else:
    # Для продакшена тоже добавляем, но обычно это делает веб-сервер
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)