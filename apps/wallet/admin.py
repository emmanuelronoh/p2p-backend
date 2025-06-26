from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from .models import (
    Currency, Wallet, Transaction,
    DepositAddress, WithdrawalLimit, ExchangeRate,
    NetworkFee, UserAddressBook
)
from .forms import CurrencyAdminForm, TransactionAdminForm
import csv
from django.http import HttpResponse

User = get_user_model()

class ExportCSVMixin:
    """Mixin to add CSV export functionality to admin classes"""
    
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={meta}.csv'
        
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])
        
        return response
    
    export_as_csv.short_description = "Export Selected as CSV"

@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin, ExportCSVMixin):
    form = CurrencyAdminForm
    list_display = (
        'code', 'name', 'type_display', 'network_display', 
        'is_active', 'min_withdrawal', 'withdrawal_fee',
        'deposit_enabled', 'withdrawal_enabled', 'trading_enabled'
    )
    list_filter = (
        'type', 'network', 'is_active', 
        'deposit_enabled', 'withdrawal_enabled', 'trading_enabled'
    )
    search_fields = ('code', 'name', 'contract_address')
    ordering = ('code',)
    readonly_fields = (
        'created_at', 'updated_at', 'deposit_address_count',
        'withdrawal_count', 'trade_count'
    )
    list_editable = (
        'is_active', 'min_withdrawal', 'withdrawal_fee',
        'deposit_enabled', 'withdrawal_enabled', 'trading_enabled'
    )
    actions = ['export_as_csv']
    
    fieldsets = (
        (None, {
            'fields': (
                'code', 'name', 'type', 'network', 'contract_address',
                'is_active', 'precision', 'confirmations_required', 'icon_url'
            )
        }),
        (_('Transaction Settings'), {
            'fields': (
                'min_withdrawal', 'min_deposit', 'withdrawal_fee',
                'withdrawal_fee_type'
            )
        }),
        (_('Feature Flags'), {
            'fields': (
                'deposit_enabled', 'withdrawal_enabled', 'trading_enabled'
            )
        }),
        (_('Statistics'), {
            'fields': (
                'deposit_address_count', 'withdrawal_count', 'trade_count'
            )
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def type_display(self, obj):
        return obj.get_type_display()
    type_display.short_description = _('Type')
    
    def network_display(self, obj):
        return obj.get_network_display()
    network_display.short_description = _('Network')
    
    def deposit_address_count(self, obj):
        return obj.depositaddress_set.count()
    deposit_address_count.short_description = _('Deposit Addresses')
    
    def withdrawal_count(self, obj):
        return obj.transaction_set.filter(type='withdrawal').count()
    withdrawal_count.short_description = _('Withdrawals')
    
    def trade_count(self, obj):
        return obj.transaction_set.filter(type='trade').count()
    trade_count.short_description = _('Trades')

class WalletInline(admin.TabularInline):
    model = Wallet
    extra = 0
    readonly_fields = (
        'currency', 'balance_display', 'locked_display', 
        'staked_display', 'available_balance', 'updated_at'
    )
    fields = (
        'currency', 'balance_display', 'locked_display',
        'staked_display', 'available_balance', 'updated_at'
    )
    
    def balance_display(self, obj):
        return f"{obj.balance:.8f}"
    balance_display.short_description = _('Balance')
    
    def locked_display(self, obj):
        return f"{obj.locked:.8f}"
    locked_display.short_description = _('Locked')
    
    def staked_display(self, obj):
        return f"{obj.staked:.8f}"
    staked_display.short_description = _('Staked')
    
    def available_balance(self, obj):
        return f"{obj.available_balance:.8f}"
    available_balance.short_description = _('Available')
    
    def has_add_permission(self, request, obj=None):
        return False

class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = (
        'short_txid', 'amount_display', 'type_display', 
        'status_display', 'network_display', 'created_at'
    )
    fields = (
        'short_txid', 'currency', 'amount_display', 
        'type_display', 'status_display', 'network_display', 'created_at'
    )
    
    def short_txid(self, obj):
        return obj.txid[:15] + '...' if obj.txid else '—'
    short_txid.short_description = _('TXID')
    
    def amount_display(self, obj):
        return f"{obj.amount:.8f} {obj.currency.code}"
    amount_display.short_description = _('Amount')
    
    def type_display(self, obj):
        return obj.get_type_display()
    type_display.short_description = _('Type')
    
    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = _('Status')
    
    def network_display(self, obj):
        return obj.network if obj.network else '—'
    network_display.short_description = _('Network')
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin, ExportCSVMixin):
    list_display = (
        'user_email', 'currency', 'balance_display', 
        'locked_display', 'staked_display', 'available_display'
    )
    list_filter = ('currency',)
    search_fields = (
        'user__email', 'user__username', 
        'currency__code', 'address'
    )
    readonly_fields = (
        'user_email', 'currency', 'balance', 
        'locked', 'staked', 'created_at', 'updated_at'
    )
    actions = ['export_as_csv']
    
    def user_email(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    user_email.admin_order_field = 'user__email'
    
    def balance_display(self, obj):
        return f"{obj.balance:.8f}"
    balance_display.short_description = _('Balance')
    
    def locked_display(self, obj):
        return f"{obj.locked:.8f}"
    locked_display.short_description = _('Locked')
    
    def staked_display(self, obj):
        return f"{obj.staked:.8f}"
    staked_display.short_description = _('Staked')
    
    def available_display(self, obj):
        return f"{obj.available_balance:.8f}"
    available_display.short_description = _('Available')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin, ExportCSVMixin):
    form = TransactionAdminForm
    list_display = (
        'short_txid', 'user_email', 'currency', 
        'amount_display', 'type_display', 'status_display',
        'network_display', 'created_at'
    )
    list_filter = (
        'type', 'status', 'currency', 'network', 'created_at'
    )
    search_fields = (
        'txid', 'user__email', 'user__username', 
        'address', 'from_address', 'to_address'
    )
    readonly_fields = (
        'user_email', 'wallet_link', 'currency', 'amount', 
        'fee', 'fee_currency', 'type', 'status', 'address',
        'txid', 'memo', 'network', 'from_address', 'to_address',
        'confirmations', 'required_confirmations', 'metadata',
        'created_at', 'updated_at', 'completed_at'
    )
    date_hierarchy = 'created_at'
    actions = ['export_as_csv', 'mark_as_completed', 'mark_as_failed']
    
    fieldsets = (
        (None, {
            'fields': (
                'user_email', 'wallet_link', 'currency',
                'fee_currency'
            )
        }),
        (_('Transaction Details'), {
            'fields': (
                'amount', 'fee', 'type', 'status',
                'network', 'confirmations', 'required_confirmations'
            )
        }),
        (_('Blockchain Info'), {
            'fields': (
                'address', 'from_address', 'to_address',
                'txid', 'memo', 'metadata'
            )
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at', 'completed_at')
        }),
    )
    
    def short_txid(self, obj):
        return obj.txid[:15] + '...' if obj.txid else '—'
    short_txid.short_description = _('TXID')
    
    def user_email(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def wallet_link(self, obj):
        if obj.wallet:
            url = reverse("admin:wallet_wallet_change", args=[obj.wallet.id])
            return format_html('<a href="{}">Wallet #{}</a>', url, obj.wallet.id)
        return '—'
    wallet_link.short_description = _('Wallet')
    
    def amount_display(self, obj):
        return f"{obj.amount:.8f} {obj.currency.code}"
    amount_display.short_description = _('Amount')
    
    def type_display(self, obj):
        return obj.get_type_display()
    type_display.short_description = _('Type')
    
    def status_display(self, obj):
        return obj.get_status_display()
    status_display.short_description = _('Status')
    
    def network_display(self, obj):
        return obj.network if obj.network else '—'
    network_display.short_description = _('Network')
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(
            request, 
            f"Successfully marked {updated} transactions as completed."
        )
    mark_as_completed.short_description = "Mark selected transactions as completed"
    
    def mark_as_failed(self, request, queryset):
        updated = queryset.filter(status='pending').update(status='failed')
        self.message_user(
            request, 
            f"Successfully marked {updated} transactions as failed."
        )
    mark_as_failed.short_description = "Mark selected transactions as failed"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user', 'wallet', 'currency', 'fee_currency'
        )

@admin.register(DepositAddress)
class DepositAddressAdmin(admin.ModelAdmin, ExportCSVMixin):
    list_display = (
        'user_email', 'currency', 'short_address', 
        'memo', 'is_active', 'created_at'
    )
    list_filter = ('currency', 'is_active', 'is_archived')
    search_fields = (
        'address', 'user__email', 'user__username', 
        'memo', 'label'
    )
    readonly_fields = (
        'user_email', 'currency', 'address', 
        'memo', 'privkey', 'created_at'
    )
    list_editable = ('is_active',)
    actions = ['export_as_csv', 'archive_addresses']
    
    def user_email(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def short_address(self, obj):
        return obj.address[:15] + '...' if obj.address else '—'
    short_address.short_description = _('Address')
    
    def archive_addresses(self, request, queryset):
        updated = queryset.update(is_active=False, is_archived=True)
        self.message_user(
            request, 
            f"Successfully archived {updated} deposit addresses."
        )
    archive_addresses.short_description = "Archive selected deposit addresses"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')

@admin.register(WithdrawalLimit)
class WithdrawalLimitAdmin(admin.ModelAdmin, ExportCSVMixin):
    list_display = (
        'user_email', 'currency', 'period_display',
        'tier_display', 'limit_display', 'used_display', 
        'remaining_display', 'reset_at', 'updated_at'
    )
    list_filter = ('currency', 'period', 'tier')
    search_fields = ('user__email', 'user__username')
    readonly_fields = (
        'user_email', 'currency', 'period', 'tier',
        'limit_amount', 'used_amount', 'reset_at', 'updated_at'
    )
    actions = ['export_as_csv']
    
    def user_email(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def period_display(self, obj):
        return obj.get_period_display()
    period_display.short_description = _('Period')
    
    def tier_display(self, obj):
        return obj.get_tier_display()
    tier_display.short_description = _('Tier')
    
    def limit_display(self, obj):
        return f"{obj.limit_amount:.8f} {obj.currency.code}"
    limit_display.short_description = _('Limit')
    
    def used_display(self, obj):
        return f"{obj.used_amount:.8f} {obj.currency.code}"
    used_display.short_description = _('Used')
    
    def remaining_display(self, obj):
        return f"{obj.remaining_amount:.8f} {obj.currency.code}"
    remaining_display.short_description = _('Remaining')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin, ExportCSVMixin):
    list_display = (
        'pair', 'rate', 'rate_type_display',
        'source', 'is_active', 'updated_at'
    )
    list_filter = (
        'is_active', 'base_currency', 'quote_currency',
        'rate_type', 'source'
    )
    search_fields = (
        'base_currency__code', 'quote_currency__code',
        'source'
    )
    list_editable = ('rate', 'is_active')
    actions = ['export_as_csv']
    
    def pair(self, obj):
        return f"{obj.base_currency.code}/{obj.quote_currency.code}"
    pair.short_description = _('Currency Pair')
    
    def rate_type_display(self, obj):
        return obj.get_rate_type_display()
    rate_type_display.short_description = _('Rate Type')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'base_currency', 'quote_currency'
        )

@admin.register(NetworkFee)
class NetworkFeeAdmin(admin.ModelAdmin, ExportCSVMixin):
    list_display = (
        'currency', 'network', 'withdrawal_fee',
        'withdrawal_min', 'deposit_enabled',
        'withdrawal_enabled', 'updated_at'
    )
    list_filter = ('currency', 'network')
    search_fields = ('currency__code', 'network')
    list_editable = (
        'withdrawal_fee', 'withdrawal_min',
        'deposit_enabled', 'withdrawal_enabled'
    )
    actions = ['export_as_csv']
    
    # You can remove these if you want raw values displayed:
    # def withdrawal_fee_display(self, obj):
    #     return f"{obj.withdrawal_fee:.8f} {obj.currency.code}"
    # withdrawal_fee_display.short_description = _('Withdrawal Fee')
    
    # def withdrawal_min_display(self, obj):
    #     return f"{obj.withdrawal_min:.8f} {obj.currency.code}"
    # withdrawal_min_display.short_description = _('Min Withdrawal')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('currency')


@admin.register(UserAddressBook)
class UserAddressBookAdmin(admin.ModelAdmin, ExportCSVMixin):
    list_display = (
        'user_email', 'currency', 'short_address',
        'address_type_display', 'label', 'is_verified',
        'created_at'
    )
    list_filter = ('currency', 'address_type', 'is_verified')
    search_fields = (
        'address', 'user__email', 'user__username',
        'label', 'memo'
    )
    list_editable = ('is_verified',)
    readonly_fields = ('user_email', 'currency', 'created_at')
    actions = ['export_as_csv']
    
    def user_email(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def short_address(self, obj):
        return obj.address[:15] + '...' if obj.address else '—'
    short_address.short_description = _('Address')
    
    def address_type_display(self, obj):
        return obj.get_address_type_display()
    address_type_display.short_description = _('Type')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')