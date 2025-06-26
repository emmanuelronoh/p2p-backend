from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from .models import (
    Currency, Wallet, Transaction,
    DepositAddress, WithdrawalLimit, ExchangeRate
)
from .serializers import (
    CurrencySerializer, WalletSerializer, TransactionSerializer,
    CreateTransactionSerializer, DepositAddressSerializer,
    CreateDepositAddressSerializer, WithdrawalLimitSerializer,
    ExchangeRateSerializer, PortfolioSummarySerializer
)
from .blockchain import BlockchainManager
from .tasks import process_withdrawal, check_deposit_status
import logging

logger = logging.getLogger(__name__)

class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Currency.objects.filter(is_active=True)
    serializer_class = CurrencySerializer
    permission_classes = [IsAuthenticated]

class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WalletSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def balances(self, request):
        wallets = self.get_queryset()
        serializer = self.get_serializer(wallets, many=True)
        return Response(serializer.data)

class TransactionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Show all transactions including deposits, withdrawals, and trades
        return Transaction.objects.filter(
            Q(user=self.request.user) |
            Q(related_user=self.request.user)
        ).order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ['create']:
            return CreateTransactionSerializer
        return TransactionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        currency = serializer.validated_data['currency']
        amount = serializer.validated_data['amount']
        tx_type = serializer.validated_data['type']
        address = serializer.validated_data.get('address')
        
        wallet, _ = Wallet.objects.get_or_create(
            user=request.user,
            currency=currency,
            defaults={'balance': 0, 'locked': 0}
        )
        
        if tx_type == 'deposit':
            # In a real system, deposits are detected by blockchain monitoring
            return Response(
                {'error': 'Deposits must come through blockchain transactions'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        elif tx_type == 'withdrawal':
            # Verify sufficient balance including pending withdrawals
            available_balance = wallet.balance - wallet.locked
            if available_balance < amount:
                return Response(
                    {'error': 'Insufficient balance'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check withdrawal limits
            limit, _ = WithdrawalLimit.objects.get_or_create(
                user=request.user,
                currency=currency,
                defaults={'limit_24h': currency.min_withdrawal * 100, 'used_24h': 0}
            )
            
            if limit.used_24h + amount > limit.limit_24h:
                return Response(
                    {'error': 'Withdrawal limit exceeded'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Lock the funds
            wallet.locked += amount
            wallet.save()
            
            # Create pending transaction
            transaction = Transaction.objects.create(
                user=request.user,
                wallet=wallet,
                currency=currency,
                amount=amount,
                type=tx_type,
                status='pending',
                address=address,
                memo=serializer.validated_data.get('memo')
            )
            
            # Process withdrawal asynchronously
            process_withdrawal.delay(transaction.id)
            
            return Response(
                TransactionSerializer(transaction).data,
                status=status.HTTP_201_CREATED
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        transaction = self.get_object()
        
        if transaction.status != 'pending':
            return Response(
                {'error': 'Only pending transactions can be canceled'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if transaction.type == 'withdrawal':
            wallet = transaction.wallet
            wallet.locked -= transaction.amount
            wallet.balance += transaction.amount  # Return the funds
            wallet.save()
            
            # Update withdrawal limit
            limit = WithdrawalLimit.objects.get(
                user=request.user,
                currency=transaction.currency
            )
            limit.used_24h -= transaction.amount
            limit.save()
        
        transaction.status = 'canceled'
        transaction.save()
        
        return Response({'status': 'canceled'})

class DepositAddressViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return DepositAddress.objects.filter(user=self.request.user, is_active=True)

    def get_serializer_class(self):
        if self.action in ['create']:
            return CreateDepositAddressSerializer
        return DepositAddressSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        currency = serializer.validated_data['currency']
        blockchain = BlockchainManager()
        
        try:
            # Generate real blockchain address
            address_info = blockchain.generate_address(currency.code)
            
            deposit_address = DepositAddress.objects.create(
                user=request.user,
                currency=currency,
                address=address_info['address'],
                privkey=address_info['privkey'],  # Should be encrypted in production
                is_active=True
            )
            
            # Start monitoring this address for deposits
            check_deposit_status.delay(deposit_address.id)
            
            return Response(
                DepositAddressSerializer(deposit_address).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            logger.error(f"Error generating deposit address: {str(e)}")
            return Response(
                {'error': 'Could not generate deposit address'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class WithdrawalLimitViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WithdrawalLimitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WithdrawalLimit.objects.filter(user=self.request.user)

class ExchangeRateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExchangeRate.objects.filter(is_active=True)
    serializer_class = ExchangeRateSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def ticker(self, request):
        base_currency = request.query_params.get('base', 'BTC')
        quote_currency = request.query_params.get('quote', 'USDT')
        
        try:
            rate = ExchangeRate.objects.get(
                base_currency__code=base_currency,
                quote_currency__code=quote_currency
            )
            return Response(ExchangeRateSerializer(rate).data)
        except ExchangeRate.DoesNotExist:
            # Try to fetch live rate if not in database
            blockchain = BlockchainManager()
            live_rate = blockchain.get_exchange_rate(base_currency, quote_currency)
            if live_rate:
                base = Currency.objects.get(code=base_currency)
                quote = Currency.objects.get(code=quote_currency)
                rate = ExchangeRate.objects.create(
                    base_currency=base,
                    quote_currency=quote,
                    rate=live_rate
                )
                return Response(ExchangeRateSerializer(rate).data)
            
            return Response(
                {'error': 'Exchange rate not found'},
                status=status.HTTP_404_NOT_FOUND
            )

class PortfolioSummaryView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PortfolioSummarySerializer

    def get(self, request):
        wallets = Wallet.objects.filter(user=request.user)
        
        # Get exchange rates for all currencies to USD
        rates = {}
        for rate in ExchangeRate.objects.filter(
            base_currency__in=[w.currency for w in wallets],
            quote_currency__code='USD'
        ):
            rates[rate.base_currency.code] = rate.rate
        
        # For currencies without rates, try to get live rates
        blockchain = BlockchainManager()
        for wallet in wallets:
            if wallet.currency.code not in rates:
                live_rate = blockchain.get_exchange_rate(wallet.currency.code, 'USD')
                if live_rate:
                    rates[wallet.currency.code] = live_rate
        
        total_balance = 0
        currencies = []
        
        for wallet in wallets:
            currency = wallet.currency
            usd_rate = rates.get(currency.code, 0)
            usd_value = (wallet.balance - wallet.locked) * usd_rate
            
            currencies.append({
                'currency': CurrencySerializer(currency).data,
                'balance': wallet.balance,
                'available': wallet.balance - wallet.locked,
                'locked': wallet.locked,
                'usd_value': usd_value,
                'usd_rate': usd_rate
            })
            
            total_balance += usd_value
        
        return Response({
            'total_balance': total_balance,
            'currencies': currencies,
            'last_updated': timezone.now()
        })