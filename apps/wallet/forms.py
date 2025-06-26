from django import forms
from django.core.exceptions import ValidationError
from .models import Currency, Transaction

class CurrencyAdminForm(forms.ModelForm):
    class Meta:
        model = Currency
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('type') == 'token' and not cleaned_data.get('contract_address'):
            raise ValidationError("Contract address is required for tokens")
        return cleaned_data

class TransactionAdminForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('type') == 'withdrawal' and not cleaned_data.get('txid'):
            if cleaned_data.get('status') == 'completed':
                raise ValidationError("TXID is required for completed withdrawals")
        return cleaned_data