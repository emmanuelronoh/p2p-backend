from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Q
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

import binascii
import nacl.signing
from datetime import datetime

from .models import TradeDispute

class DisputeResolutionForm(forms.ModelForm):
    ADMIN_SIGNING_KEY = getattr(settings, 'DISPUTE_ADMIN_SIGNING_KEY', None)
    
    resolution_notes = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text="Internal notes about the resolution decision"
    )
    
    class Meta:
        model = TradeDispute
        fields = ['resolution', 'resolution_notes', 'admin_sig']
        widgets = {
            'admin_sig': forms.HiddenInput()
        }
    
    def clean(self):
        cleaned_data = super().clean()
        resolution = cleaned_data.get('resolution')
        
        if resolution != 0:  # If not pending
            if not self.ADMIN_SIGNING_KEY:
                raise ValidationError("Admin signing key not configured")
            
            # Generate signature
            signing_key = nacl.signing.SigningKey(self.ADMIN_SIGNING_KEY)
            message = f"{self.instance.id}{resolution}".encode()
            signature = signing_key.sign(message).signature
            cleaned_data['admin_sig'] = binascii.hexlify(signature).decode()
            
            # Auto-set resolved_at if not set
            if not self.instance.resolved_at:
                self.instance.resolved_at = datetime.now()
        
        return cleaned_data


@admin.register(TradeDispute)
class TradeDisputeAdmin(admin.ModelAdmin):
    form = DisputeResolutionForm
    list_display = (
        'id', 
        'trade_link', 
        'initiator_token', 
        'resolution_status', 
        'created_at', 
        'resolved_at',
        'evidence_links',
        'action_buttons'
    )
    list_filter = ('resolution', 'created_at', 'resolved_at')
    search_fields = ('trade__id', 'initiator_token')
    readonly_fields = (
        'trade_details', 
        'initiator_token', 
        'created_at', 
        'evidence_preview',
        'verification_status'
    )
    fieldsets = (
        (_('Dispute Information'), {
            'fields': ('trade_details', 'initiator_token', 'created_at', 'resolved_at')
        }),
        (_('Evidence'), {
            'fields': ('evidence_preview', 'evidence_ipfs_cid')
        }),
        (_('Resolution'), {
            'fields': (
                'resolution', 
                'resolution_notes',
                'admin_sig',
                'verification_status'
            )
        }),
    )
    actions = ['mark_as_pending', 'favor_buyer', 'favor_seller', 'split_funds']
    list_per_page = 20
    date_hierarchy = 'created_at'
    list_select_related = ('trade',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # For non-superusers, only show disputes that need attention
            qs = qs.filter(resolution=0)
        return qs
    
    def trade_link(self, obj):
        url = reverse('admin:p2p_p2ptrade_change', args=[obj.trade.id])
        return format_html('<a href="{}">{}</a>', url, obj.trade.id)
    trade_link.short_description = _('Trade ID')
    trade_link.admin_order_field = 'trade__id'
    
    def resolution_status(self, obj):
        colors = {
            0: 'orange',  # Pending
            1: 'blue',     # Buyer
            2: 'red',      # Seller
            3: 'purple',   # Split
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors[obj.resolution],
            obj.get_resolution_display()
        )
    resolution_status.short_description = _('Status')
    
    def evidence_links(self, obj):
        links = []
        if obj.evidence_ipfs_cid:
            ipfs_url = f"https://ipfs.io/ipfs/{obj.evidence_ipfs_cid}"
            links.append(format_html(
                '<a href="{}" target="_blank" style="margin-right: 10px;">IPFS Evidence</a>',
                ipfs_url
            ))
        
        if obj.evidence_hashes:
            links.append(format_html(
                '<a href="#" onclick="alert(\'Hashes: {}\')">View Hashes</a>',
                obj.evidence_hashes
            ))
        
        return format_html(''.join(links)) if links else '-'
    evidence_links.short_description = _('Evidence')
    
    def action_buttons(self, obj):
        buttons = []
        if obj.resolution == 0:  # Pending
            buttons.append(format_html(
                '<a href="{}" class="button" style="background: #4CAF50; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none;">Resolve</a>',
                reverse('admin:disputes_tradedispute_change', args=[obj.id])
            ))
        else:
            buttons.append(format_html(
                '<a href="{}" class="button" style="background: #2196F3; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none;">View</a>',
                reverse('admin:disputes_tradedispute_change', args=[obj.id])
            ))
        return format_html(''.join(buttons))
    action_buttons.short_description = _('Actions')
    action_buttons.allow_tags = True
    
    def trade_details(self, obj):
        return format_html(
            '''
            <div style="padding: 10px; background: #f8f8f8; border-radius: 5px;">
                <strong>Trade ID:</strong> {}<br>
                <strong>Amount:</strong> {} {}<br>
                <strong>Parties:</strong> Buyer {}, Seller {}
            </div>
            ''',
            obj.trade.id,
            obj.trade.amount,
            obj.trade.currency,
            obj.trade.buyer_token[:8] + '...',
            obj.trade.seller_token[:8] + '...'
        )
    trade_details.short_description = _('Trade Details')
    
    def evidence_preview(self, obj):
        if not obj.evidence_hashes and not obj.evidence_ipfs_cid:
            return '-'
        
        preview = []
        if obj.evidence_ipfs_cid:
            preview.append(format_html(
                '<p><strong>IPFS CID:</strong> {}</p>',
                obj.evidence_ipfs_cid
            ))
        
        if obj.evidence_hashes:
            try:
                hashes = obj.evidence_hashes.split(',')
                preview.append(format_html(
                    '<p><strong>Evidence Hashes:</strong></p><ul style="max-height: 100px; overflow-y: auto;">{}</ul>',
                    ''.join([f'<li style="font-family: monospace;">{h}</li>' for h in hashes[:5]])
                ))
                if len(hashes) > 5:
                    preview.append(format_html(
                        '<p>+ {} more hashes...</p>',
                        len(hashes) - 5
                    ))
            except:
                preview.append(format_html(
                    '<p><strong>Evidence Hashes:</strong> {}</p>',
                    obj.evidence_hashes
                ))
        
        return format_html(''.join(preview))
    evidence_preview.short_description = _('Evidence Preview')
    
    def verification_status(self, obj):
        if not obj.admin_sig or not obj.resolution:
            return format_html(
                '<span style="color: orange;">⚠ Not signed</span>'
            )
        
        try:
            verify_key = nacl.signing.VerifyKey(settings.DISPUTE_ADMIN_PUBKEY)
            message = f"{obj.id}{obj.resolution}".encode()
            verify_key.verify(message, binascii.unhexlify(obj.admin_sig))
            return format_html(
                '<span style="color: green;">✓ Verified</span>'
            )
        except:
            return format_html(
                '<span style="color: red;">✗ Invalid signature</span>'
            )
    verification_status.short_description = _('Verification')
    
    # Custom actions
    def mark_as_pending(self, request, queryset):
        queryset.update(resolution=0, admin_sig=None)
        self.message_user(request, "Selected disputes marked as pending", messages.SUCCESS)
    mark_as_pending.short_description = "Mark selected as pending"
    
    def favor_buyer(self, request, queryset):
        self._resolve_disputes(request, queryset, 1, "Buyer favored")
    favor_buyer.short_description = "Resolve in favor of buyer"
    
    def favor_seller(self, request, queryset):
        self._resolve_disputes(request, queryset, 2, "Seller favored")
    favor_seller.short_description = "Resolve in favor of seller"
    
    def split_funds(self, request, queryset):
        self._resolve_disputes(request, queryset, 3, "Funds split")
    split_funds.short_description = "Resolve by splitting funds"
    
    def _resolve_disputes(self, request, queryset, resolution, message):
        signing_key = nacl.signing.SigningKey(settings.DISPUTE_ADMIN_SIGNING_KEY)
        updated = 0
        
        for dispute in queryset:
            message_to_sign = f"{dispute.id}{resolution}".encode()
            signature = signing_key.sign(message_to_sign).signature
            dispute.resolution = resolution
            dispute.admin_sig = binascii.hexlify(signature).decode()
            dispute.resolved_at = datetime.now()
            dispute.save()
            updated += 1
        
        self.message_user(
            request, 
            f"{updated} disputes resolved - {message}", 
            messages.SUCCESS
        )
    
    def get_list_display_links(self, request, list_display):
        # Only link the ID field if superuser to prevent accidental clicks
        if request.user.is_superuser:
            return super().get_list_display_links(request, list_display)
        return (None,)
    
    class Media:
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css',
                'css/disputes_admin.css',
            )
        }
        js = (
            'https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js',
            'js/disputes_admin.js',
        )