from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CurrencyViewSet, WalletViewSet, TransactionViewSet,
    DepositAddressViewSet, WithdrawalLimitViewSet,
    ExchangeRateViewSet, PortfolioSummaryView
)

router = DefaultRouter()
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'wallets', WalletViewSet, basename='wallet')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'deposit-addresses', DepositAddressViewSet, basename='deposit-address')
router.register(r'withdrawal-limits', WithdrawalLimitViewSet, basename='withdrawal-limit')
router.register(r'exchange-rates', ExchangeRateViewSet, basename='exchange-rate')

urlpatterns = [
    path('', include(router.urls)),
    path('wallet/portfolio/summary/', PortfolioSummaryView.as_view(), name='portfolio-summary'),
    
    # Additional endpoints
    path('wallet/balances/', WalletViewSet.as_view({'get': 'balances'}), name='wallet-balances'),
    path('wallet/exchange-rates/ticker/', ExchangeRateViewSet.as_view({'get': 'ticker'}), name='exchange-rate-ticker'),
]