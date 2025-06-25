from django.urls import path
from .views import (
    NetworkListView, TokenListView, TokenNetworkListView,
    QuoteCreateView, InitiateBridgeView, BridgeStatusView,
    BridgeHistoryView, EstimateTimeView, FeeListView, StatsView
)

urlpatterns = [
    path('networks/', NetworkListView.as_view(), name='bridge-networks'),
    path('tokens/', TokenListView.as_view(), name='bridge-tokens'),
    path('tokens/<uuid:token_id>/networks/', TokenNetworkListView.as_view(), name='bridge-token-networks'),
    path('quote/', QuoteCreateView.as_view(), name='bridge-quote'),
    path('initiate/', InitiateBridgeView.as_view(), name='bridge-initiate'),
    path('status/<uuid:id>/', BridgeStatusView.as_view(), name='bridge-status'),
    path('history/', BridgeHistoryView.as_view(), name='bridge-history'),
    path('estimate-time/', EstimateTimeView.as_view(), name='bridge-estimate-time'),
    path('fees/', FeeListView.as_view(), name='bridge-fees'),
    path('stats/', StatsView.as_view(), name='bridge-stats'),
]