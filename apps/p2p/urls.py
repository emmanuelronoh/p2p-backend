from django.urls import path
from .views import (
    P2PListingListView,
    P2PListingDetailView,
    P2PTradeCreateView,
    P2PTradeDetailView,
    MyTradesListView,
    MarketStatsView,
    SpecificUserView,
    MarkTradeAsPaidView, 
)

urlpatterns = [
    path('listings/', P2PListingListView.as_view(), name='p2p-listing-list'),
    path('listings/<uuid:pk>/', P2PListingDetailView.as_view(), name='p2p-listing-detail'),
    path('trades/', P2PTradeCreateView.as_view(), name='p2p-trade-create'),
    path('trades/<uuid:pk>/', P2PTradeDetailView.as_view(), name='p2p-trade-detail'),
    path('trades/<uuid:pk>/mark-paid/', MarkTradeAsPaidView.as_view(), name='p2p-trade-mark-paid'),
    path('my-trades/', MyTradesListView.as_view(), name='p2p-my-trades'),
    path('market-stats/', MarketStatsView.as_view(), name='p2p-market-stats'),
    path('specific-user/', SpecificUserView.as_view(), name='p2p-specific-user'),
]
