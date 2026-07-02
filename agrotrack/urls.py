"""
URL configuration for AgroTrack project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1
    path('api/v1/auth/', include('accounts.urls', namespace='accounts')),

    # OpenAPI 3 Schema & Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/docs/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
