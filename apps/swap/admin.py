from django.contrib import admin
from .models import (
    SwapToken, SwapRoute, SwapQuote,
    SwapTransaction, SwapAllowance,
    SwapPrice, MarketStats
)

class SwapTokenAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name', 'network', 'is_active', 'min_swap_amount')
    list_filter = ('network', 'is_active')
    search_fields = ('symbol', 'name', 'contract_address')
    ordering = ('symbol',)
    readonly_fields = ('decimals',)

class SwapRouteAdmin(admin.ModelAdmin):
    list_display = ('token_in', 'token_out', 'is_active', 'fee_percentage', 'min_amount_in', 'max_amount_in')
    list_filter = ('is_active', 'token_in__network', 'token_out__network')
    search_fields = ('token_in__symbol', 'token_out__symbol')
    raw_id_fields = ('token_in', 'token_out')

class SwapQuoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'token_in', 'token_out', 'amount_in', 'amount_out', 'rate', 'valid_until')
    list_filter = ('token_in__network', 'token_out__network')
    search_fields = ('token_in__symbol', 'token_out__symbol', 'id')
    raw_id_fields = ('token_in', 'token_out')
    readonly_fields = ('created_at',)

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing an existing object
            return self.readonly_fields + ('token_in', 'token_out', 'amount_in', 'amount_out', 'rate', 'fee_amount', 'valid_until')
        return self.readonly_fields

class SwapTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'quote_summary', 'user_token_short', 'created_at')
    list_filter = ('status', 'quote__token_in__network', 'quote__token_out__network')
    search_fields = ('tx_hash', 'quote__id', 'from_address', 'to_address')
    readonly_fields = ('created_at', 'executed_at', 'completed_at')
    raw_id_fields = ('quote',)

    def quote_summary(self, obj):
        return f"{obj.quote.amount_in} {obj.quote.token_in.symbol} → {obj.quote.amount_out} {obj.quote.token_out.symbol}"
    quote_summary.short_description = 'Swap'

    def user_token_short(self, obj):
        return obj.user_token[:8] + '...' if obj.user_token else ''
    user_token_short.short_description = 'User Token'

class SwapAllowanceAdmin(admin.ModelAdmin):
    list_display = ('user_token_short', 'token', 'contract_address_short', 'allowance_amount', 'last_updated')
    list_filter = ('token__network',)
    search_fields = ('user_token', 'token__symbol', 'contract_address')
    readonly_fields = ('last_updated',)
    raw_id_fields = ('token',)

    def user_token_short(self, obj):
        return obj.user_token[:8] + '...' if obj.user_token else ''
    user_token_short.short_description = 'User Token'

    def contract_address_short(self, obj):
        return obj.contract_address[:8] + '...' + obj.contract_address[-4:]
    contract_address_short.short_description = 'Contract'

class SwapPriceAdmin(admin.ModelAdmin):
    list_display = ('token', 'price_usd', 'timestamp')
    list_filter = ('token__network',)
    search_fields = ('token__symbol',)
    readonly_fields = ('timestamp',)
    raw_id_fields = ('token',)

class MarketStatsAdmin(admin.ModelAdmin):
    list_display = ('token_pair', 'volume_24h', 'high_24h', 'low_24h', 'change_24h', 'last_updated')
    search_fields = ('token_pair',)
    readonly_fields = ('last_updated',)

admin.site.register(SwapToken, SwapTokenAdmin)
admin.site.register(SwapRoute, SwapRouteAdmin)
admin.site.register(SwapQuote, SwapQuoteAdmin)
admin.site.register(SwapTransaction, SwapTransactionAdmin)
admin.site.register(SwapAllowance, SwapAllowanceAdmin)
admin.site.register(SwapPrice, SwapPriceAdmin)
admin.site.register(MarketStats, MarketStatsAdmin)