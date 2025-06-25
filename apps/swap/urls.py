from django.urls import path
from .views import (
    TokenListView, RouteListView, QuoteCreateView,
    ExecuteSwapView, SwapStatusView, SwapHistoryView,
    PriceListView, MarketStatsView, AllowanceView
)

urlpatterns = [
    path('tokens/', TokenListView.as_view(), name='swap-tokens'),
    path('routes/', RouteListView.as_view(), name='swap-routes'),
    path('quote/', QuoteCreateView.as_view(), name='swap-quote'),
    path('execute/', ExecuteSwapView.as_view(), name='swap-execute'),
    path('status/<uuid:tx_id>/', SwapStatusView.as_view(), name='swap-status'),
    path('history/', SwapHistoryView.as_view(), name='swap-history'),
    path('prices/', PriceListView.as_view(), name='swap-prices'),
    path('market-stats/', MarketStatsView.as_view(), name='swap-market-stats'),
    path('allowance/', AllowanceView.as_view(), name='swap-allowance'),
]