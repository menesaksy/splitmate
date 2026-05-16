from django import forms
from django.contrib.auth.models import User
from .models import Group, Expense, ExpenseShare, Settlement, Category
from decimal import Decimal


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'description', 'currency']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Örn: Ev Arkadaşları'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'currency': forms.Select(
                attrs={'class': 'form-select'},
                choices=[('TRY', '₺ TRY'), ('USD', '$ USD'), ('EUR', '€ EUR')]
            ),
        }


class ExpenseForm(forms.ModelForm):
    """Harcama ekleme formu. shares alanı view'de manuel işlenir."""
    class Meta:
        model = Expense
        fields = ['title', 'description', 'amount', 'paid_by', 'category', 'split_type', 'date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'paid_by': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'split_type': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        group = kwargs.pop('group', None)
        super().__init__(*args, **kwargs)
        if group is not None:
            # paid_by listesi sadece grup üyeleri olsun
            self.fields['paid_by'].queryset = group.members.all()
        self.fields['category'].required = False

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Tutar sıfırdan büyük olmalı.")
        return amount


class SettlementForm(forms.ModelForm):
    class Meta:
        model = Settlement
        fields = ['from_user', 'to_user', 'amount', 'note', 'date']
        widgets = {
            'from_user': forms.Select(attrs={'class': 'form-select'}),
            'to_user': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'note': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        group = kwargs.pop('group', None)
        super().__init__(*args, **kwargs)
        if group is not None:
            members = group.members.all()
            self.fields['from_user'].queryset = members
            self.fields['to_user'].queryset = members

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('from_user') == cleaned.get('to_user'):
            raise forms.ValidationError("Kendine ödeme yapamazsın.")
        return cleaned


class JoinGroupForm(forms.Form):
    invite_code = forms.CharField(
        max_length=12,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Davet kodu',
            'style': 'font-family: monospace; letter-spacing: 2px;'
        })
    )