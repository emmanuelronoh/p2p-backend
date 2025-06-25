from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.core.urls')),
    path('api/escrow/', include('apps.escrow.urls')),
    path('api/p2p/', include('apps.p2p.urls')),
    path('api/disputes/', include('apps.disputes.urls')),
    path('api/', include('apps.wallet.urls')),
    path('swap/', include('apps.swap.urls')),
    path('bridge/', include('apps.bridge.urls')),
]