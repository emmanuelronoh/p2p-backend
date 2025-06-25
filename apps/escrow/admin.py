from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum
from .models import (
    EscrowWallet,
    SystemWallet,
    TransactionQueue,
    EscrowDispute,
    EscrowAuditLog
)

@admin.register(EscrowWallet)
class EscrowWalletAdmin(admin.ModelAdmin):
    list_display = (
        'short_id',
        'truncated_address',
        'status_badge',
        'amount_display',
        'buyer_address_short',
        'seller_address_short',
        'created_at',
        'last_used',
        'wallet_actions'  # Changed from transaction_actions to 'wallet_actions'
    )
    list_filter = ('status', 'created_at', 'last_used')
    search_fields = ('address', 'user_token', 'buyer_address', 'seller_address')
    readonly_fields = ('id', 'address', 'user_token', 'created_at', 'last_used')
    list_per_page = 20
    actions = ['mark_as_funded', 'mark_as_released', 'mark_as_disputed']
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'address', 'user_token', 'status')
        }),
        ('Balance Information', {
            'fields': ('amount', 'balance_commitment')
        }),
        ('Participant Addresses', {
            'fields': ('buyer_address', 'seller_address')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_used')
        }),
    )

    def short_id(self, obj):
        return str(obj.id)[:8]
    short_id.short_description = 'ID'

    def truncated_address(self, obj):
        return f"{obj.address[:6]}...{obj.address[-4:]}"
    truncated_address.short_description = 'Address'

    def status_badge(self, obj):
        status_colors = {
            'created': 'blue',
            'funded': 'green',
            'released': 'gray',
            'disputed': 'orange',
        }
        return format_html(
            '<span style="padding: 2px 6px; border-radius: 4px; background-color: {}; color: white;">{}</span>',
            status_colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def amount_display(self, obj):
        return f"{obj.amount} USDT" if obj.amount else "-"
    amount_display.short_description = 'Amount'

    def buyer_address_short(self, obj):
        return obj.buyer_address[:10] + '...' if obj.buyer_address else "-"
    buyer_address_short.short_description = 'Buyer'

    def seller_address_short(self, obj):
        return obj.seller_address[:10] + '...' if obj.seller_address else "-"
    seller_address_short.short_description = 'Seller'

    def wallet_actions(self, obj):
        """Custom action buttons for individual wallets"""
        buttons = []
        if obj.status == 'funded':
            buttons.append(
                f'<a href="/admin/escrow/escrowwallet/{obj.id}/release/" class="button" style="padding: 2px 5px; background: #417690; color: white; border-radius: 4px; text-decoration: none;">Release</a>'
            )
        if obj.status in ['created', 'funded']:
            buttons.append(
                f'<a href="/admin/escrow/escrowwallet/{obj.id}/dispute/" class="button" style="padding: 2px 5px; background: #ba2121; color: white; border-radius: 4px; text-decoration: none;">Dispute</a>'
            )
        return format_html(' '.join(buttons)) if buttons else "-"
    wallet_actions.short_description = 'Actions'  # Changed from transaction_actions to a string
    wallet_actions.allow_tags = True

    # Bulk actions
    def mark_as_funded(self, request, queryset):
        updated = queryset.update(status='funded')
        self.message_user(request, f"{updated} escrow(s) marked as funded")
    mark_as_funded.short_description = "Mark selected as funded"

    def mark_as_released(self, request, queryset):
        updated = queryset.update(status='released')
        self.message_user(request, f"{updated} escrow(s) marked as released")
    mark_as_released.short_description = "Mark selected as released"

    def mark_as_disputed(self, request, queryset):
        updated = queryset.update(status='disputed')
        self.message_user(request, f"{updated} escrow(s) marked as disputed")
    mark_as_disputed.short_description = "Mark selected as disputed"

    def get_actions(self, request):
        """Ensure actions are properly registered"""
        actions = super().get_actions(request)
        # Remove the delete action if not needed
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    

@admin.register(EscrowDispute)
class EscrowDisputeAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'escrow_link',
        'status_badge',
        'initiator_short',
        'created_date',
        'resolved_date',
        'transaction_actions'  # Fixed: added quotes
    )
    list_filter = ('status', 'created_at', 'resolved_at')
    search_fields = ('escrow__address', 'initiator', 'reason')
    readonly_fields = ('created_at',)
    actions = ['mark_as_resolved']
    raw_id_fields = ('escrow',)

    def escrow_link(self, obj):
        url = f"/admin/escrow/escrowwallet/{obj.escrow.id}/"
        return format_html('<a href="{}">{}</a>', url, obj.escrow.address)
    escrow_link.short_description = 'Escrow'

    def status_badge(self, obj):
        status_colors = {
            1: 'orange',  # Open
            2: 'blue',  # In Review
            3: 'green',  # Resolved
        }
        return format_html(
            '<span style="padding: 2px 6px; border-radius: 4px; background-color: {}; color: white;">{}</span>',
            status_colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def initiator_short(self, obj):
        return obj.initiator[:10] + '...' if obj.initiator else "-"
    initiator_short.short_description = 'Initiator'

    def created_date(self, obj):
        return obj.created_at.strftime("%Y-%m-%d")
    created_date.short_description = 'Created'

    def resolved_date(self, obj):
        return obj.resolved_at.strftime("%Y-%m-%d") if obj.resolved_at else "-"
    resolved_date.short_description = 'Resolved'

    def transaction_actions(self, obj):
        if obj.status != 3:  # Not resolved
            return format_html(
                '<a href="/admin/escrow/escrowdispute/{}/resolve/" class="button">Resolve</a>',
                obj.id
            )
        return "-"
    transaction_actions.short_description = 'Actions'  # Fixed: changed to string
    transaction_actions.allow_tags = True  # Added this to allow HTML rendering

    def mark_as_resolved(self, request, queryset):
        from .tasks import resolve_disputes
        dispute_ids = list(queryset.values_list('id', flat=True))
        resolve_disputes.delay(dispute_ids)
        self.message_user(request, f"Marked {len(dispute_ids)} disputes as resolved")
    mark_as_resolved.short_description = "Mark as resolved"

    
@admin.register(SystemWallet)
class SystemWalletAdmin(admin.ModelAdmin):
    list_display = (
        'truncated_address',
        'current_balance_display',
        'collected_fees_display',
        'last_swept',
        'total_value'
    )
    readonly_fields = ('address', 'current_balance', 'collected_fees', 'last_swept_at')
    actions = ['sweep_funds']

    def truncated_address(self, obj):
        return f"{obj.address[:6]}...{obj.address[-4:]}"
    truncated_address.short_description = 'Address'

    def current_balance_display(self, obj):
        return f"{obj.current_balance} USDT"
    current_balance_display.short_description = 'Balance'

    def collected_fees_display(self, obj):
        return f"{obj.collected_fees} USDT"
    collected_fees_display.short_description = 'Fees Collected'

    def last_swept(self, obj):
        return obj.last_swept_at.strftime("%Y-%m-%d %H:%M") if obj.last_swept_at else "Never"
    last_swept.short_description = 'Last Swept'

    def total_value(self, obj):
        total = (obj.current_balance or 0) + (obj.collected_fees or 0)
        return f"{total} USDT"
    total_value.short_description = 'Total Value'

    def sweep_funds(self, request, queryset):
        from .tasks import sweep_funds_to_cold_storage
        for wallet in queryset:
            sweep_funds_to_cold_storage.delay(wallet.address)
        self.message_user(request, "Sweep initiated for selected wallets")
    sweep_funds.short_description = "Sweep funds to cold storage"

@admin.register(TransactionQueue)
class TransactionQueueAdmin(admin.ModelAdmin):
    list_display = (
        'short_hash',
        'type_display',
        'status_badge',
        'created_time',
        'processed_time',
        'retry_count'
    )
    list_filter = ('status', 'tx_type', 'created_at')
    search_fields = ('tx_hash',)
    readonly_fields = ('tx_hash', 'tx_type', 'status', 'created_at', 'processed_at')
    actions = ['retry_failed']

    def short_hash(self, obj):
        return f"{obj.tx_hash[:10]}..." if obj.tx_hash else "-"
    short_hash.short_description = 'Transaction'

    def type_display(self, obj):
        return obj.tx_type.capitalize()
    type_display.short_description = 'Type'

    def status_badge(self, obj):
        status_colors = {
            1: 'blue',  # Pending
            2: 'orange',  # Processing
            3: 'green',  # Completed
            4: 'red',  # Failed
        }
        return format_html(
            '<span style="padding: 2px 6px; border-radius: 4px; background-color: {}; color: white;">{}</span>',
            status_colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def created_time(self, obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M")
    created_time.short_description = 'Created'

    def processed_time(self, obj):
        return obj.processed_at.strftime("%Y-%m-%d %H:%M") if obj.processed_at else "-"
    processed_time.short_description = 'Processed'

    def retry_failed(self, request, queryset):
        from .tasks import retry_transactions
        transaction_ids = list(queryset.values_list('id', flat=True))
        retry_transactions.delay(transaction_ids)
        self.message_user(request, f"Retrying {len(transaction_ids)} failed transactions")
    retry_failed.short_description = "Retry failed transactions"


@admin.register(EscrowAuditLog)
class EscrowAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'action_badge',
        'escrow_link',
        'ip_address',
        'created_time',
        'details_preview'
    )
    list_filter = ('action', 'created_at')
    search_fields = ('escrow__address', 'ip_address', 'details')
    readonly_fields = ('escrow', 'action', 'details', 'created_at', 'ip_address')
    date_hierarchy = 'created_at'

    def action_badge(self, obj):
        action_colors = {
            'CREATE': 'blue',
            'FUND': 'green',
            'RELEASE': 'purple',
            'DISPUTE': 'orange',
        }
        return format_html(
            '<span style="padding: 2px 6px; border-radius: 4px; background-color: {}; color: white;">{}</span>',
            action_colors.get(obj.action, 'gray'),
            obj.get_action_display()
        )
    action_badge.short_description = 'Action'

    def escrow_link(self, obj):
        url = f"/admin/escrow/escrowwallet/{obj.escrow.id}/"
        return format_html('<a href="{}">{}</a>', url, obj.escrow.address)
    escrow_link.short_description = 'Escrow'

    def created_time(self, obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M")
    created_time.short_description = 'Timestamp'

    def details_preview(self, obj):
        return str(obj.details)[:50] + '...' if obj.details else "-"
    details_preview.short_description = 'Details'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False