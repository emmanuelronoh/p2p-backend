from django.urls import path
from .views import (
    TradeDisputeCreateView,
    TradeDisputeDetailView,
    TradeDisputeListView
)

urlpatterns = [
    path('', TradeDisputeListView.as_view(), name='dispute-list'),
    path('create/', TradeDisputeCreateView.as_view(), name='dispute-create'),
    path('<uuid:pk>/', TradeDisputeDetailView.as_view(), name='dispute-detail'),
]

