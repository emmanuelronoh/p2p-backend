from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from .models import AnonymousUser, SecurityEvent, SecurityQuestion

class SecurityQuestionInline(admin.TabularInline):
    model = SecurityQuestion
    extra = 0
    fields = ('id', 'question_preview', 'created_at', 'last_used')
    readonly_fields = ('id', 'question_preview', 'created_at', 'last_used')
    
    def question_preview(self, obj):
        return format_html(
            '<span title="Question ID: {}" style="font-weight:500;">{}</span>',
            obj.id,
            "Security Question (encrypted)" if obj.question_enc else "Not set"
        )
    question_preview.short_description = "Question"

class SecurityEventInline(admin.TabularInline):
    
    model = SecurityEvent
    extra = 0
    fields = ('event_type_display', 'created_at', 'ip_hmac_short')
    readonly_fields = ('event_type_display', 'created_at', 'ip_hmac_short')
    
    def event_type_display(self, obj):
        return obj.get_event_type_display()
    event_type_display.short_description = "Event Type"
    
    def ip_hmac_short(self, obj):
        return obj.ip_hmac[:8] + "..." if obj.ip_hmac else "N/A"
    ip_hmac_short.short_description = "IP Hash"
    
    def has_add_permission(self, request, obj=None):
        return False

@admin.register(AnonymousUser)
class AnonymousUserAdmin(UserAdmin):
    list_display = ('exchange_code', 'username', 'email', 'trust_score', 'is_active', 'created_at')
    list_filter = ('is_active', 'is_staff', 'is_superuser', 'trust_score')
    search_fields = ('exchange_code', 'username', 'email', 'client_token')
    ordering = ('-created_at',)
    readonly_fields = ('exchange_code', 'client_token', 'created_at', 'last_active')
    fieldsets = (
        (None, {'fields': ('exchange_code', 'client_token', 'password')}),
        (_('Personal Info'), {'fields': ('username', 'email', 'phone', 'location', 'bio', 'avatar_url')}),
        (_('Stats'), {'fields': ('trust_score', 'total_trades', 'success_rate')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_active', 'created_at', 'deleted_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('exchange_code', 'password1', 'password2'),
        }),
    )
    inlines = [SecurityQuestionInline, SecurityEventInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('security_questions', 'security_events')

@admin.register(SecurityEvent)
class SecurityEventAdmin(admin.ModelAdmin):
    list_display = ('event_type_display', 'actor_display', 'ip_short', 'created_at')
    list_filter = ('event_type', 'created_at')
    search_fields = ('actor_token', 'ip_hmac')
    readonly_fields = ('id', 'event_type', 'actor_token', 'ip_hmac', 'details_decrypted', 'created_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        (None, {'fields': ('id', 'event_type', 'created_at')}),
        (_('Actor'), {'fields': ('actor_token',)}),
        (_('Network'), {'fields': ('ip_hmac',)}),
        (_('Details'), {'fields': ('details_decrypted',)}),
    )
    
    def event_type_display(self, obj):
        return obj.get_event_type_display()
    event_type_display.short_description = "Event Type"
    
    def actor_display(self, obj):
        if not obj.actor_token:
            return "System"
        try:
            user = AnonymousUser.objects.get(client_token=obj.actor_token)
            url = reverse("admin:core_anonymoususer_change", args=[user.id])
            return format_html('<a href="{}">{}</a>', url, user.exchange_code)
        except AnonymousUser.DoesNotExist:
            return obj.actor_token[:8] + "..."
    actor_display.short_description = "Actor"
    
    def ip_short(self, obj):
        return obj.ip_hmac[:8] + "..." if obj.ip_hmac else "N/A"
    ip_short.short_description = "IP Hash"
    
    def details_decrypted(self, obj):
        try:
            return obj.details_enc  # In a real implementation, you would decrypt this
        except:
            return "Unable to decrypt"
    details_decrypted.short_description = "Event Details"

@admin.register(SecurityQuestion)
class SecurityQuestionAdmin(admin.ModelAdmin):
    list_display = ('user_display', 'question_preview', 'created_at', 'last_used')
    list_filter = ('created_at', 'last_used')
    search_fields = ('user__exchange_code', 'user__username')
    readonly_fields = ('id', 'user', 'question_decrypted', 'answer_decrypted', 'created_at', 'last_used')
    
    fieldsets = (
        (None, {'fields': ('id', 'user', 'created_at', 'last_used')}),
        (_('Question'), {'fields': ('question_decrypted',)}),
        (_('Answer'), {'fields': ('answer_decrypted',)}),
    )
    
    def user_display(self, obj):
        url = reverse("admin:core_anonymoususer_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.exchange_code)
    user_display.short_description = "User"
    
    def question_preview(self, obj):
        return "Security Question (encrypted)" if obj.question_enc else "Not set"
    question_preview.short_description = "Question"
    
    def question_decrypted(self, obj):
        try:
            return obj.decrypt_data(obj.question_enc)
        except:
            return "Unable to decrypt"
    question_decrypted.short_description = "Decrypted Question"
    
    def answer_decrypted(self, obj):
        try:
            return "*****" + obj.decrypt_data(obj.answer_enc)[-2:]  # Show only last 2 chars for security
        except:
            return "Unable to decrypt"
    answer_decrypted.short_description = "Decrypted Answer (partial)"