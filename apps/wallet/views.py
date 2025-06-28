from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import (
    Currency, Wallet, Transaction,
    DepositAddress, WithdrawalLimit, ExchangeRate
)
from .serializers import (
    CurrencySerializer, WalletSerializer, TransactionSerializer,
    CreateTransactionSerializer, DepositAddressSerializer,
    CreateDepositAddressSerializer, WithdrawalLimitSerializer,
    ExchangeRateSerializer, PortfolioSummarySerializer, SetWalletAddressSerializer
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
        # First ensure all currency wallets exist for the user
        self._ensure_wallets_exist()
        # Then sync with blockchain
        self._sync_blockchain_balances()
        return Wallet.objects.filter(user=self.request.user)

    def _ensure_wallets_exist(self):
        """Ensure wallet exists for all active currencies"""
        active_currencies = Currency.objects.filter(is_active=True)
        for currency in active_currencies:
            Wallet.objects.get_or_create(
                user=self.request.user,
                currency=currency,
                defaults={
                    'balance': 0,
                    'locked': 0,
                    'address': self._generate_wallet_address(currency)
                }
            )

    def _generate_wallet_address(self, currency):
        """Generate a new wallet address if needed"""
        if currency.code in ['BTC', 'ETH', 'USDT']:
            blockchain = BlockchainManager()
            try:
                address_info = blockchain.generate_address(currency.code)
                return address_info['address']
            except Exception as e:
                logger.error(f"Error generating {currency.code} address: {str(e)}")
        return ''
    
    @action(detail=False, methods=['post'], url_path='set-wallet-address')
    def set_wallet_address(self, request):
        serializer = SetWalletAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
    
        address = serializer.validated_data['address']
        code = serializer.validated_data['currency']
    
        try:
            currency = Currency.objects.get(code=code)
        except Currency.DoesNotExist:
            return Response({'error': 'Currency not found'}, status=status.HTTP_404_NOT_FOUND)

        wallet, _ = Wallet.objects.get_or_create(user=request.user, currency=currency)
        wallet.address = address
        wallet.save()

        return Response({'message': 'Wallet address updated successfully'})


    def _sync_blockchain_balances(self):
        """Sync wallet balances with actual blockchain balances"""
        blockchain = BlockchainManager()
        wallets = Wallet.objects.filter(user=self.request.user)
        
        for wallet in wallets:
            try:
                # Skip if no address assigned
                if not wallet.address:
                    continue
                    
                # Get actual balance from blockchain
                if wallet.currency.code == 'USDT':
                    balance = blockchain.get_erc20_balance(wallet.address, 'USDT')
                elif wallet.currency.code == 'ETH':
                    balance = blockchain.get_eth_balance(wallet.address)
                elif wallet.currency.code == 'BTC':
                    balance = blockchain.get_btc_balance(wallet.address)
                else:
                    continue
                
                # Update wallet balance if different
                if wallet.balance != balance:
                    wallet.balance = balance
                    wallet.save()
                    logger.info(f"Updated {wallet.currency.code} balance for {wallet.address}")
                    
            except Exception as e:
                logger.error(f"Error syncing {wallet.currency.code} balance: {str(e)}")
                continue

    @action(detail=False, methods=['get'])
    def balances(self, request):
        wallets = self.get_queryset()
        if not wallets.exists():
            # If no wallets, ensure they're created
            self._ensure_wallets_exist()
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
        amount = Decimal(str(serializer.validated_data['amount']))  # Ensure decimal
        tx_type = serializer.validated_data['type']
        address = serializer.validated_data.get('address')
        network = serializer.validated_data.get('network')
        memo = serializer.validated_data.get('memo', '')
        
        # Additional validation for USDT
        if currency.code == 'USDT':
            if not network or network not in ['ERC20', 'TRC20']:
                return Response(
                    {'error': 'Network required for USDT transactions (ERC20/TRC20)'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if len(memo) > 120:  # USDT memos are typically shorter
                return Response(
                    {'error': 'Memo too long for USDT transaction'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        wallet, _ = Wallet.objects.get_or_create(
            user=request.user,
            currency=currency,
            defaults={'balance': 0, 'locked': 0}
        )
        
        if tx_type == 'deposit':
            # For USDT deposits, we should have detected via blockchain monitoring
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
            
            # Additional checks for minimum withdrawal amounts
            if amount < currency.min_withdrawal:
                return Response(
                    {'error': f'Amount below minimum withdrawal of {currency.min_withdrawal}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check withdrawal limits
            limit, _ = WithdrawalLimit.objects.get_or_create(
                user=request.user,
                currency=currency,
                defaults={'limit_24h': currency.min_withdrawal * 100, 'used_24h': 0}
            )
            
            # Calculate potential new usage
            new_used = limit.used_24h + amount
            
            if new_used > limit.limit_24h:
                remaining = limit.limit_24h - limit.used_24h
                return Response(
                    {
                        'error': 'Withdrawal limit exceeded',
                        'remaining_limit': remaining,
                        'max_allowed': remaining
                    },
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
                memo=memo,
                network=network if currency.code == 'USDT' else None
            )
            
            # Process withdrawal asynchronously
            process_withdrawal.delay(transaction.id)
            
            # Update limit immediately (will be reverted if transaction fails)
            limit.used_24h = new_used
            limit.save()
            
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

    @action(detail=False, methods=['get'])
    def withdrawal_info(self, request):
        """Get withdrawal information (limits, fees, etc.)"""
        currencies = Currency.objects.filter(withdrawal_enabled=True)
        
        data = []
        for currency in currencies:
            limit, _ = WithdrawalLimit.objects.get_or_create(
                user=request.user,
                currency=currency,
                defaults={'limit_24h': currency.min_withdrawal * 100, 'used_24h': 0}
            )
            
            currency_data = {
                'currency': CurrencySerializer(currency).data,
                'limit_24h': limit.limit_24h,
                'used_24h': limit.used_24h,
                'remaining': limit.limit_24h - limit.used_24h,
                'min_withdrawal': currency.min_withdrawal,
                'withdrawal_fee': currency.withdrawal_fee,
            }
            
            if currency.code == 'USDT':
                currency_data['networks'] = [
                    {'id': 'ERC20', 'name': 'Ethereum (ERC20)'},
                    {'id': 'TRC20', 'name': 'Tron (TRC20)'}
                ]
            
            data.append(currency_data)
        
        return Response(data)

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Check transaction status on blockchain"""
        transaction = self.get_object()
        
        if not transaction.txid:
            return Response({'status': transaction.status})
        
        blockchain = BlockchainManager()
        
        try:
            if transaction.currency.code == 'BTC':
                status_info = blockchain.get_transaction_status('BTC', transaction.txid)
            elif transaction.currency.code == 'USDT':
                status_info = blockchain.get_transaction_status(
                    'USDT', 
                    transaction.txid,
                    network=transaction.network
                )
            elif transaction.currency.code == 'ETH':
                status_info = blockchain.get_transaction_status('ETH', transaction.txid)
            else:
                return Response({'status': transaction.status})
            
            # Update transaction status if changed
            if status_info['status'] != transaction.status:
                transaction.status = status_info['status']
                if status_info['status'] == 'confirmed':
                    transaction.completed_at = timezone.now()
                    # Only unlock if it was a withdrawal
                    if transaction.type == 'withdrawal':
                        transaction.wallet.locked -= transaction.amount
                        transaction.wallet.save()
                transaction.save()
            
            return Response(status_info)
        except Exception as e:
            logger.error(f"Error checking transaction status: {str(e)}")
            return Response({'status': transaction.status})

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
    

