# p2p/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count, Sum, Avg, F
from django.utils import timezone
from datetime import timedelta
from django.contrib.admin import SimpleListFilter
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django import forms
from .models import P2PListing, P2PTrade
from apps.escrow.models import EscrowWallet
import uuid

User = get_user_model()

class ActiveListingsFilter(SimpleListFilter):
    title = 'Active Status'
    parameter_name = 'active_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active Listings'),
            ('expired', 'Expired Listings'),
            ('funded', 'Funded Listings'),
            ('reserved', 'Reserved Listings'),
            ('completed', 'Completed Listings'),
        )

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == 'active':
            return queryset.filter(status=1, expires_at__gt=now)
        elif self.value() == 'expired':
            return queryset.filter(expires_at__lte=now)
        elif self.value() == 'funded':
            return queryset.filter(status=2)
        elif self.value() == 'reserved':
            return queryset.filter(status=3)
        elif self.value() == 'completed':
            return queryset.filter(status=4)
        return queryset

class TradeStatusFilter(SimpleListFilter):
    title = 'Trade Status'
    parameter_name = 'trade_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active Trades (Funded/PaymentSent)'),
            ('completed', 'Completed Trades'),
            ('disputed', 'Disputed Trades'),
            ('recent_24h', 'Recent (24h)'),
            ('recent_7d', 'Recent (7 days)'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(status__in=[1, 2])
        elif self.value() == 'completed':
            return queryset.filter(status=3)
        elif self.value() == 'disputed':
            return queryset.filter(status=4)
        elif self.value() == 'recent_24h':
            return queryset.filter(created_at__gte=timezone.now()-timedelta(days=1))
        elif self.value() == 'recent_7d':
            return queryset.filter(created_at__gte=timezone.now()-timedelta(days=7))
        return queryset

class P2PListingForm(forms.ModelForm):
    class Meta:
        model = P2PListing
        fields = '__all__'
        
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('status') == 2 and not cleaned_data.get('escrow_wallet'):
            raise ValidationError("Funded listings must have an escrow wallet")
        return cleaned_data

@admin.register(P2PListing)
class P2PListingAdmin(admin.ModelAdmin):
    form = P2PListingForm
    list_display = (
        'truncated_id',
        'crypto_type_display',
        'amounts_display',
        'payment_method_display',
        'status_display',
        'user_info',
        'time_info',
        'listing_actions'  # Changed from transaction_actions to 'listing_actions'
    )
    list_filter = (
        ActiveListingsFilter,
        'crypto_type',
        'payment_method',
        'created_at',
    )
    search_fields = ('id', 'seller_token', 'description', 'escrow_wallet__address')
    readonly_fields = (
        'id', 
        'created_at', 
        'expires_at', 
        'seller_token',
        'escrow_wallet_link',
        'trades_count',
        'total_volume'
    )
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'seller_token', 'status', 'escrow_wallet_link')
        }),
        ('Listing Details', {
            'fields': (
                'crypto_type',
                'crypto_currency',
                'crypto_amount',
                'fiat_currency',
                'usdt_amount',
                'payment_method',
                'description',
                'instructions_enc'
            )
        }),
        ('Statistics', {
            'fields': ('trades_count', 'total_volume'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'expires_at')
        }),
    )
    actions = [
        'mark_as_funded', 
        'expire_listings',
        'renew_listings',
        'clone_listings'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 50
    list_select_related = ('escrow_wallet',)
    ordering = ('-created_at',)
    save_on_top = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            trades_count=Count('trades'),
            total_volume=Sum('trades__usdt_amount')
        )

    def truncated_id(self, obj):
        return str(obj.id)[:8]
    truncated_id.short_description = 'ID'
    truncated_id.admin_order_field = 'id'

    def crypto_type_display(self, obj):
        color = 'green' if obj.crypto_type == 'buy' else 'red'
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_crypto_type_display().upper()
        )
    crypto_type_display.short_description = 'Type'

    
    def amounts_display(self, obj):
        return format_html(
          'Amount: {}',
          "${:.2f}".format(obj.usdt_amount) if obj.usdt_amount is not None else "$0.00"
        )
    def payment_method_display(self, obj):
        methods = {
            1: ('Cash', '#4CAF50'),
            2: ('Hawala', '#2196F3'),
            3: ('Other', '#9E9E9E')
        }
        text, color = methods.get(obj.payment_method, ('Unknown', 'black'))
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            text
        )
    payment_method_display.short_description = 'Payment'
    payment_method_display.admin_order_field = 'payment_method'

    def status_display(self, obj):
        status_map = {
            1: ('Active', 'green'),
            2: ('Funded', 'blue'),
            3: ('Reserved', 'orange'),
            4: ('Completed', 'gray'),
            5: ('Expired', 'red')
        }
        status, color = status_map.get(obj.status, ('Unknown', 'black'))
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'

    def user_info(self, obj):
        return format_html(
            'Seller: {}<br>Escrow: {}',
            obj.seller_token[:8] + '...',
            obj.escrow_wallet.address[:10] + '...' if obj.escrow_wallet else 'None'
        )
    user_info.short_description = 'Parties'

    def time_info(self, obj):
        now = timezone.now()
        if obj.expires_at > now:
            delta = obj.expires_at - now
            expires = f"In {delta.days}d {delta.seconds//3600}h"
        else:
            expires = "Expired"
        
        return format_html(
            'Created: {}<br>Expires: {}',
            obj.created_at.strftime('%Y-%m-%d %H:%M'),
            expires
        )
    time_info.short_description = 'Timeline'

    def escrow_wallet_link(self, obj):
        if obj.escrow_wallet:
            url = reverse('admin:escrow_escrowwallet_change', args=[obj.escrow_wallet.id])
            return format_html('<a href="{}">{}</a>', url, obj.escrow_wallet.address)
        return "-"
    escrow_wallet_link.short_description = 'Escrow Wallet'

    def trades_count(self, obj):
        return obj.trades_count
    trades_count.short_description = 'Trades Count'
    trades_count.admin_order_field = 'trades_count'

    def total_volume(self, obj):
        return f"${obj.total_volume:.2f}" if obj.total_volume else "$0.00"
    total_volume.short_description = 'Total Volume'
    total_volume.admin_order_field = 'total_volume'

    def listing_actions(self, obj):
        """Custom action buttons for individual listings"""
        view_url = reverse('admin:p2p_p2plisting_change', args=[obj.id])
        trades_url = reverse('admin:p2p_p2ptrade_changelist') + f'?listing__id__exact={obj.id}'
        return format_html(
            '<a href="{}" class="button" style="padding: 2px 5px; background: #417690; color: white; border-radius: 4px; text-decoration: none; margin-right: 5px;">View</a>'
            '<a href="{}" class="button" style="padding: 2px 5px; background: #5a6268; color: white; border-radius: 4px; text-decoration: none;">Trades</a>',
            view_url,
            trades_url
        )
    listing_actions.short_description = 'Actions'
    listing_actions.allow_tags = True

    # Bulk actions
    def mark_as_funded(self, request, queryset):
        updated = queryset.filter(status=1).update(status=2)
        self.message_user(request, f"{updated} listings marked as funded.")
    mark_as_funded.short_description = "Mark selected as funded"

    def expire_listings(self, request, queryset):
        updated = queryset.filter(status__in=[1,2,3], expires_at__gt=timezone.now()).update(status=5)
        self.message_user(request, f"{updated} listings expired.")
    expire_listings.short_description = "Expire selected listings"

    def renew_listings(self, request, queryset):
        renewed = 0
        for listing in queryset:
            if listing.status == 5:  # Only renew expired listings
                listing.status = 1
                listing.expires_at = timezone.now() + timedelta(days=7)
                listing.save()
                renewed += 1
        self.message_user(request, f"{renewed} listings renewed.")
    renew_listings.short_description = "Renew expired listings"

    def clone_listings(self, request, queryset):
        cloned = 0
        for listing in queryset:
            if listing.status in [1, 2, 5]:  # Only clone active, funded or expired
                new_listing = P2PListing(
                    seller_token=listing.seller_token,
                    crypto_type=listing.crypto_type,
                    crypto_currency=listing.crypto_currency,
                    crypto_amount=listing.crypto_amount,
                    fiat_currency=listing.fiat_currency,
                    usdt_amount=listing.usdt_amount,
                    payment_method=listing.payment_method,
                    description=listing.description,
                    status=1,
                )
                new_listing.save()
                cloned += 1
        self.message_user(request, f"{cloned} listings cloned.")
    clone_listings.short_description = "Clone selected listings"

    def get_actions(self, request):
        """Ensure actions are properly registered"""
        actions = super().get_actions(request)
        # Remove the delete action if not needed
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    

class P2PTradeForm(forms.ModelForm):
    class Meta:
        model = P2PTrade
        fields = '__all__'
        
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('status') == 3 and not cleaned_data.get('completed_at'):
            cleaned_data['completed_at'] = timezone.now()
        return cleaned_data

@admin.register(P2PTrade)
class P2PTradeAdmin(admin.ModelAdmin):
    form = P2PTradeForm
    list_display = (
        'truncated_id',
        'listing_link',
        'status_display',
        'amounts_display',
        'fee_display',
        'parties_display',
        'timeline_display',
        'transaction_actions'
    )
    list_filter = (
        TradeStatusFilter,
        'created_at',
        'updated_at',
    )
    search_fields = (
        'id', 
        'buyer_token', 
        'seller_token', 
        'escrow_tx_hash',
        'payment_proof_hash',
        'listing__id'
    )
    readonly_fields = (
        'id', 
        'created_at', 
        'updated_at', 
        'completed_at',
        'buyer_token',
        'seller_token',
        'listing_link',
        'fee_amount',
        'usdt_amount'
    )
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'listing_link', 'status')
        }),
        ('Parties', {
            'fields': ('buyer_token', 'seller_token')
        }),
        ('Transaction Details', {
            'fields': ('escrow_tx_hash', 'payment_proof_hash')
        }),
        ('Financials', {
            'fields': ('usdt_amount', 'fee_amount')
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at', 'completed_at')
        }),
    )
    actions = [
        'mark_as_completed', 
        'mark_as_disputed',
        'cancel_trades'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 50
    list_select_related = ('listing',)
    ordering = ('-created_at',)
    save_on_top = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('listing')

    def truncated_id(self, obj):
        return str(obj.id)[:8]
    truncated_id.short_description = 'ID'
    truncated_id.admin_order_field = 'id'

    def listing_link(self, obj):
        url = reverse('admin:p2p_p2plisting_change', args=[obj.listing.id])
        return format_html('<a href="{}">{}</a>', url, str(obj.listing.id)[:8])
    listing_link.short_description = 'Listing'
    listing_link.admin_order_field = 'listing__id'

    def status_display(self, obj):
        status_map = {
            0: ('Created', 'gray'),
            1: ('Funded', 'blue'),
            2: ('PaymentSent', 'orange'),
            3: ('Completed', 'green'),
            4: ('Disputed', 'red'),
            5: ('Canceled', 'black')
        }
        status, color = status_map.get(obj.status, ('Unknown', 'black'))
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            status
        )
    status_display.short_description = 'Status'
    status_display.admin_order_field = 'status'

    def amounts_display(self, obj):
        usdt_amount = "${:.2f}".format(float(obj.usdt_amount)) if obj.usdt_amount is not None else "$0.00"
        fee_amount = "${:.6f}".format(float(obj.fee_amount)) if obj.fee_amount is not None else "$0.00"
        return format_html(
            'Amount: {}<br>Fee: {}',
            usdt_amount,
            fee_amount
        )
    amounts_display.short_description = 'Amounts'
    amounts_display.admin_order_field = 'usdt_amount'

    def fee_display(self, obj):
        try:
           # Ensure we're working with numeric values
           fee_amount = float(obj.fee_amount) if obj.fee_amount is not None else 0.0
           usdt_amount = float(obj.usdt_amount) if obj.usdt_amount is not None else 0.0
        
           fee_formatted = "${:.6f}".format(fee_amount)
           fee_percent = (fee_amount / usdt_amount * 100) if usdt_amount else 0
        
           return format_html(
              '{}<br>({:.2f}%)',
               fee_formatted,
               fee_percent
            )
        except (TypeError, ValueError):

         return format_html('$0.00<br>(0.00%)')


    def parties_display(self, obj):
        return format_html(
            'Buyer: {}<br>Seller: {}',
            obj.buyer_token[:8] + '...',
            obj.seller_token[:8] + '...'
        )
    parties_display.short_description = 'Parties'

    def timeline_display(self, obj):
        completed = obj.completed_at.strftime('%Y-%m-%d %H:%M') if obj.completed_at else 'N/A'
        return format_html(
            'Created: {}<br>Completed: {}',
            obj.created_at.strftime('%Y-%m-%d %H:%M'),
            completed
        )
    timeline_display.short_description = 'Timeline'

    def transaction_actions(self, obj):
        view_url = reverse('admin:p2p_p2ptrade_change', args=[obj.id])
        return format_html(
            '<a href="{}" class="button">View</a>',
            view_url
        )
    transaction_actions.short_description = 'Actions'

    def mark_as_completed(self, request, queryset):
        updated = queryset.filter(status__in=[1,2]).update(
            status=3,
            completed_at=timezone.now()
        )
        self.message_user(request, f"{updated} trades marked as completed.")
    mark_as_completed.short_description = "Mark as completed"

    def mark_as_disputed(self, request, queryset):
        updated = queryset.filter(status__in=[1,2]).update(status=4)
        self.message_user(request, f"{updated} trades marked as disputed.")
    mark_as_disputed.short_description = "Mark as disputed"

    def cancel_trades(self, request, queryset):
        updated = queryset.filter(status__in=[0,1,2]).update(status=5)
        self.message_user(request, f"{updated} trades canceled.")
    cancel_trades.short_description = "Cancel trades"


# Admin customization
admin.site.site_header = "P2P Trading Platform Administration"
admin.site.site_title = "P2P Trading Admin Portal"
admin.site.index_title = "Welcome to P2P Trading Platform Admin"