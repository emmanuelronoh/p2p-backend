from django.contrib import admin
from django.contrib.auth import get_user_model
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import (
    Currency, Wallet, Transaction,
    DepositAddress, WithdrawalLimit, ExchangeRate
)

User = get_user_model()

class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'type', 'is_active', 'min_withdrawal', 'withdrawal_fee', 'precision')
    list_filter = ('type', 'is_active')
    search_fields = ('code', 'name')
    ordering = ('code',)
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active', 'min_withdrawal', 'withdrawal_fee')
    fieldsets = (
        (None, {'fields': ('code', 'name', 'type', 'is_active', 'precision')}),
        (_('Withdrawal Settings'), {'fields': ('min_withdrawal', 'withdrawal_fee')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )

class WalletInline(admin.TabularInline):
    model = Wallet
    extra = 0
    readonly_fields = ('balance_display', 'locked_display', 'available_balance', 'updated_at')
    fields = ('currency', 'balance_display', 'locked_display', 'available_balance', 'updated_at')
    
    def balance_display(self, obj):
        return f"{obj.balance:.8f}"
    balance_display.short_description = _('Balance')
    
    def locked_display(self, obj):
        return f"{obj.locked:.8f}"
    locked_display.short_description = _('Locked')
    
    def available_balance(self, obj):
        return f"{(obj.balance - obj.locked):.8f}"
    available_balance.short_description = _('Available')
    
    def has_add_permission(self, request, obj=None):
        return False

class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = ('short_txid', 'amount_display', 'type', 'status', 'created_at')
    fields = ('short_txid', 'currency', 'amount_display', 'type', 'status', 'created_at')
    
    def short_txid(self, obj):
        return obj.txid[:15] + '...' if obj.txid else '—'
    short_txid.short_description = _('TXID')
    
    def amount_display(self, obj):
        return f"{obj.amount:.8f} {obj.currency.code}"
    amount_display.short_description = _('Amount')
    
    def has_add_permission(self, request, obj=None):
        return False

class DepositAddressInline(admin.TabularInline):
    model = DepositAddress
    extra = 0
    readonly_fields = ('short_address', 'is_active', 'created_at')
    fields = ('currency', 'short_address', 'memo', 'is_active', 'created_at')
    
    def short_address(self, obj):
        return obj.address[:15] + '...' if obj.address else '—'
    short_address.short_description = _('Address')
    
    def has_add_permission(self, request, obj=None):
        return True

class WithdrawalLimitInline(admin.TabularInline):
    model = WithdrawalLimit
    extra = 0
    readonly_fields = ('limit_display', 'used_display', 'remaining_display', 'updated_at')
    fields = ('currency', 'limit_display', 'used_display', 'remaining_display', 'updated_at')
    
    def limit_display(self, obj):
        return f"{obj.limit_24h:.8f} {obj.currency.code}"
    limit_display.short_description = _('24h Limit')
    
    def used_display(self, obj):
        return f"{obj.used_24h:.8f} {obj.currency.code}"
    used_display.short_description = _('24h Used')
    
    def remaining_display(self, obj):
        remaining = obj.limit_24h - obj.used_24h
        return f"{remaining:.8f} {obj.currency.code}"
    remaining_display.short_description = _('24h Remaining')
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'currency', 'balance_display', 'locked_display', 'available_display')
    list_filter = ('currency',)
    search_fields = ('user__email', 'user__username', 'currency__code')
    readonly_fields = ('user_email', 'currency', 'balance', 'locked', 'created_at', 'updated_at')
    
    def user_email(self, obj):
        url = reverse("admin:core_anonymoususer_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    user_email.admin_order_field = 'user__email'
    
    def balance_display(self, obj):
        return f"{obj.balance:.8f}"
    balance_display.short_description = _('Balance')
    
    def locked_display(self, obj):
        return f"{obj.locked:.8f}"
    locked_display.short_description = _('Locked')
    
    def available_display(self, obj):
        return f"{(obj.balance - obj.locked):.8f}"
    available_display.short_description = _('Available')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('txid_short', 'user_email', 'currency', 'amount_display', 'type', 'status', 'created_at')
    list_filter = ('type', 'status', 'currency', 'created_at')
    search_fields = ('txid', 'user__email', 'user__username', 'address')
    readonly_fields = (
        'user_email', 'wallet_link', 'currency', 'amount', 'fee', 
        'type', 'status', 'address', 'txid', 'memo', 'created_at', 'updated_at'
    )
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {'fields': ('user_email', 'wallet_link', 'currency')}),
        (_('Transaction Details'), {'fields': ('amount', 'fee', 'type', 'status')}),
        (_('Blockchain Info'), {'fields': ('address', 'txid', 'memo')}),
        (_('Timestamps'), {'fields': ('created_at', 'updated_at')}),
    )
    
    def txid_short(self, obj):
        return obj.txid[:15] + '...' if obj.txid else '—'
    txid_short.short_description = _('TXID')
    
    def user_email(self, obj):
        url = reverse("admin:core_anonymoususer_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def wallet_link(self, obj):
        url = reverse("admin:wallet_wallet_change", args=[obj.wallet.id])
        return format_html('<a href="{}">Wallet #{}</a>', url, obj.wallet.id)
    wallet_link.short_description = _('Wallet')
    
    def amount_display(self, obj):
        return f"{obj.amount:.8f} {obj.currency.code}"
    amount_display.short_description = _('Amount')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'wallet', 'currency')

@admin.register(DepositAddress)
class DepositAddressAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'currency', 'short_address', 'memo', 'is_active', 'created_at')
    list_filter = ('currency', 'is_active')
    search_fields = ('address', 'user__email', 'user__username', 'memo')
    readonly_fields = ('user_email', 'currency', 'address', 'memo', 'created_at')
    list_editable = ('is_active',)
    
    def user_email(self, obj):
        url = reverse("admin:core_anonymoususer_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def short_address(self, obj):
        return obj.address[:15] + '...' if obj.address else '—'
    short_address.short_description = _('Address')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')

@admin.register(WithdrawalLimit)
class WithdrawalLimitAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'currency', 'limit_display', 'used_display', 'remaining_display', 'updated_at')
    list_filter = ('currency',)
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('user_email', 'currency', 'limit_24h', 'used_24h', 'updated_at')
    
    def user_email(self, obj):
        url = reverse("admin:core_anonymoususer_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)
    user_email.short_description = _('User')
    
    def limit_display(self, obj):
        return f"{obj.limit_24h:.8f} {obj.currency.code}"
    limit_display.short_description = _('24h Limit')
    
    def used_display(self, obj):
        return f"{obj.used_24h:.8f} {obj.currency.code}"
    used_display.short_description = _('24h Used')
    
    def remaining_display(self, obj):
        remaining = obj.limit_24h - obj.used_24h
        return f"{remaining:.8f} {obj.currency.code}"
    remaining_display.short_description = _('24h Remaining')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'currency')

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('pair', 'rate', 'is_active', 'updated_at')
    list_filter = ('is_active', 'base_currency', 'quote_currency')
    search_fields = ('base_currency__code', 'quote_currency__code')
    list_editable = ('rate', 'is_active')
    
    def pair(self, obj):
        return f"{obj.base_currency.code}/{obj.quote_currency.code}"
    pair.short_description = _('Currency Pair')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('base_currency', 'quote_currency')

# Register your models with their custom admin classes
admin.site.register(Currency, CurrencyAdmin)