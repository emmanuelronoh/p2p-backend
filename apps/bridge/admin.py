from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.urls import reverse
from .models import (
    BridgeNetwork, BridgeToken, BridgeTokenNetwork,
    BridgeQuote, BridgeTransaction, BridgeFee, BridgeStats
)

class BridgeTokenNetworkInline(admin.TabularInline):
    model = BridgeTokenNetwork
    extra = 1
    autocomplete_fields = ('network',)
    fields = ('network', 'contract_address', 'min_bridge_amount', 'is_active')
    verbose_name = "Network Configuration"
    verbose_name_plural = "Network Configurations"

@admin.register(BridgeNetwork)
class BridgeNetworkAdmin(admin.ModelAdmin):
    list_display = ('name', 'chain_id', 'native_token_symbol', 'is_active', 'explorer_link')
    list_filter = ('is_active',)
    search_fields = ('name', 'native_token_symbol', 'chain_id')
    readonly_fields = ('chain_id', 'explorer_link')
    list_editable = ('is_active',)
    fieldsets = (
        (None, {
            'fields': ('name', 'chain_id', 'native_token_symbol', 'is_active')
        }),
        ('Connection', {
            'fields': ('rpc_url', 'explorer_url', 'explorer_link')
        }),
    )

    def explorer_link(self, obj):
        if obj.explorer_url:
            return format_html('<a href="{}" target="_blank">Explore</a>', obj.explorer_url)
        return "-"
    explorer_link.short_description = "Explorer"

@admin.register(BridgeToken)
class BridgeTokenAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name', 'contract_address_short', 'is_active', 'network_count')
    list_filter = ('is_active',)
    search_fields = ('symbol', 'name', 'contract_address')
    readonly_fields = ('symbol', 'decimals', 'contract_address_short')
    inlines = [BridgeTokenNetworkInline]
    fieldsets = (
        (None, {
            'fields': ('symbol', 'name', 'is_active')
        }),
        ('Details', {
            'fields': ('contract_address', 'contract_address_short', 'decimals')
        }),
    )

    def contract_address_short(self, obj):
        if obj.contract_address:
            return f"{obj.contract_address[:6]}...{obj.contract_address[-4:]}"
        return "-"
    contract_address_short.short_description = "Contract (short)"

    def network_count(self, obj):
        return obj.networks.count()
    network_count.short_description = "# Networks"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('networks')

@admin.register(BridgeTokenNetwork)
class BridgeTokenNetworkAdmin(admin.ModelAdmin):
    list_display = ('token', 'network', 'contract_address_short', 'min_bridge_amount', 'is_active')
    list_filter = ('is_active', 'network', 'token')
    search_fields = ('token__symbol', 'network__name', 'contract_address')
    autocomplete_fields = ('token', 'network')
    list_editable = ('min_bridge_amount', 'is_active')
    fieldsets = (
        (None, {
            'fields': ('token', 'network', 'is_active')
        }),
        ('Configuration', {
            'fields': ('contract_address', 'min_bridge_amount')
        }),
    )

    def contract_address_short(self, obj):
        if obj.contract_address:
            return f"{obj.contract_address[:6]}...{obj.contract_address[-4:]}"
        return "-"
    contract_address_short.short_description = "Contract (short)"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('token', 'network')

@admin.register(BridgeQuote)
class BridgeQuoteAdmin(admin.ModelAdmin):
    list_display = ('id_short', 'token', 'amount', 'from_network', 'to_network', 'fee_amount', 'valid_until', 'is_valid')
    list_filter = ('from_network', 'to_network', 'token')
    search_fields = ('token__symbol', 'id')
    readonly_fields = ('id', 'created_at', 'is_valid')
    date_hierarchy = 'created_at'
    list_select_related = ('token', 'from_network', 'to_network')

    def id_short(self, obj):
        return str(obj.id)[:8]
    id_short.short_description = "ID"

    def is_valid(self, obj):
        return obj.valid_until > timezone.now()
    is_valid.boolean = True
    is_valid.short_description = "Valid?"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'token', 'from_network', 'to_network'
        )

@admin.register(BridgeTransaction)
class BridgeTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'id_short', 
        'status', 
        'from_address_short',
        'to_address_short', 
        'quote_link', 
        'initiated_at', 
        'completion_time', 
        'is_completed',
        'transaction_actions'
    )
    list_filter = ('status', 'quote__from_network', 'quote__to_network')
    search_fields = ('from_address', 'to_address', 'deposit_tx_hash', 'receive_tx_hash', 'id')
    readonly_fields = ('id', 'initiated_at', 'completed_at', 'is_completed')
    date_hierarchy = 'initiated_at'
    actions = ['mark_as_completed', 'mark_as_failed']
    list_select_related = ('quote__token', 'quote__from_network', 'quote__to_network')

    def id_short(self, obj):
        return str(obj.id)[:8]
    id_short.short_description = "ID"

    def from_address_short(self, obj):
        return f"{obj.from_address[:6]}...{obj.from_address[-4:]}"
    from_address_short.short_description = 'From'

    def to_address_short(self, obj):
        return f"{obj.to_address[:6]}...{obj.to_address[-4:]}"
    to_address_short.short_description = 'To'

    def quote_link(self, obj):
        if obj.quote:
            url = reverse('admin:bridge_bridgequote_change', args=[obj.quote.id])
            return format_html('<a href="{}">{}</a>', url, str(obj.quote.id)[:8])
        return "-"
    quote_link.short_description = 'Quote'

    def completion_time(self, obj):
        if obj.initiated_at and obj.completed_at:
            delta = obj.completed_at - obj.initiated_at
            return f"{delta.seconds // 60}m {delta.seconds % 60}s"
        return "-"
    completion_time.short_description = 'Duration'

    def is_completed(self, obj):
        return obj.status == 'completed'
    is_completed.boolean = True
    is_completed.short_description = 'Completed?'

    def transaction_actions(self, obj):
        """Custom action buttons for individual transactions"""
        view_url = reverse('admin:bridge_bridgetransaction_change', args=[obj.id])
        return format_html(
            '<a href="{}" class="button" style="padding: 2px 5px; background: #417690; color: white; border-radius: 4px; text-decoration: none;">View</a>',
            view_url
        )
    transaction_actions.short_description = 'Actions'
    transaction_actions.allow_tags = True

    # Bulk actions
    def mark_as_completed(self, request, queryset):
        updated = queryset.exclude(status='completed').update(
            status='completed',
            completed_at=timezone.now()
        )
        self.message_user(request, f"{updated} transactions marked as completed")
    mark_as_completed.short_description = "Mark as completed"

    def mark_as_failed(self, request, queryset):
        updated = queryset.exclude(status='failed').update(
            status='failed',
            completed_at=timezone.now()
        )
        self.message_user(request, f"{updated} transactions marked as failed")
    mark_as_failed.short_description = "Mark as failed"
    


@admin.register(BridgeFee)
class BridgeFeeAdmin(admin.ModelAdmin):
    list_display = ('from_network', 'to_network', 'token', 'fee_percentage', 'min_fee', 'max_fee')
    list_filter = ('from_network', 'to_network', 'token')
    search_fields = ('token__symbol',)
    autocomplete_fields = ('from_network', 'to_network', 'token')
    list_editable = ('fee_percentage', 'min_fee', 'max_fee')
    list_select_related = ('from_network', 'to_network', 'token')

@admin.register(BridgeStats)
class BridgeStatsAdmin(admin.ModelAdmin):
    list_display = ('network_pair', 'total_volume', 'total_transactions', 'avg_completion_time', 'last_updated')
    search_fields = ('network_pair',)
    readonly_fields = ('last_updated',)
    list_editable = ('total_volume', 'total_transactions', 'avg_completion_time')
    date_hierarchy = 'last_updated'

    def has_add_permission(self, request):
        return False  # Stats are typically auto-generated, not manually added