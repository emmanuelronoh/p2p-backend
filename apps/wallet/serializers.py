from rest_framework import serializers
from .models import (
    Currency, Wallet, Transaction, 
    DepositAddress, WithdrawalLimit, ExchangeRate
)
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ['code', 'name', 'type', 'is_active', 'min_withdrawal', 
                 'withdrawal_fee', 'precision', 'created_at']

class WalletSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    available = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ['id', 'currency', 'balance', 'locked', 'available', 'updated_at']

    def get_available(self, obj):
        return obj.balance - obj.locked

class TransactionSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    wallet = WalletSerializer()

    class Meta:
        model = Transaction
        fields = ['id', 'wallet', 'currency', 'amount', 'fee', 'type', 
                 'status', 'address', 'txid', 'memo', 'created_at']

class CreateTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['currency', 'amount', 'type', 'address', 'memo']

    def validate(self, data):
        if data['type'] == 'withdrawal':
            wallet = Wallet.objects.get(
                user=self.context['request'].user,
                currency=data['currency']
            )
            if wallet.balance < data['amount']:
                raise ValidationError("Insufficient balance")
        return data

class DepositAddressSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()

    class Meta:
        model = DepositAddress
        fields = ['id', 'currency', 'address', 'memo', 'is_active', 'created_at']

class CreateDepositAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = DepositAddress
        fields = ['currency']

class WithdrawalLimitSerializer(serializers.ModelSerializer):
    currency = CurrencySerializer()
    remaining = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalLimit
        fields = ['currency', 'limit_24h', 'used_24h', 'remaining', 'updated_at']

    def get_remaining(self, obj):
        return obj.limit_24h - obj.used_24h

class ExchangeRateSerializer(serializers.ModelSerializer):
    base_currency = CurrencySerializer()
    quote_currency = CurrencySerializer()

    class Meta:
        model = ExchangeRate
        fields = ['base_currency', 'quote_currency', 'rate', 'updated_at']

class PortfolioSummarySerializer(serializers.Serializer):
    total_balance = serializers.DecimalField(max_digits=20, decimal_places=2)
    currencies = serializers.ListField(child=serializers.DictField())
    last_updated = serializers.DateTimeField()