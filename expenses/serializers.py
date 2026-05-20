from rest_framework import serializers
from .models import Group, Expense, ExpenseShare, Settlement, Category
from django.contrib.auth.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'icon', 'color']


class ExpenseShareSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpenseShare
        fields = ['id', 'user', 'amount']


class ExpenseSerializer(serializers.ModelSerializer):
    paid_by = UserSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    shares = ExpenseShareSerializer(many=True, read_only=True)

    class Meta:
        model = Expense
        fields = ['id', 'title', 'description', 'amount', 'paid_by',
                  'category', 'split_type', 'date', 'created_at', 'shares']
        read_only_fields = ['created_at']


class ExpenseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ['id', 'title', 'description', 'amount', 'paid_by',
                  'category', 'split_type', 'date', 'group']
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Tutar sıfırdan büyük olmalı.')
        return value

    def validate(self, attrs):
        group = attrs.get('group')
        paid_by = attrs.get('paid_by')
        if group and paid_by:
            if not group.members.filter(id=paid_by.id).exists():
                raise serializers.ValidationError(
                    {'paid_by': 'Ödeme yapan kişi grubun üyesi olmalı.'}
                )
        return attrs


class SettlementSerializer(serializers.ModelSerializer):
    from_user = UserSerializer(read_only=True)
    to_user = UserSerializer(read_only=True)

    class Meta:
        model = Settlement
        fields = ['id', 'from_user', 'to_user', 'amount', 'note', 'date']


class SettlementWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settlement
        fields = ['id', 'group', 'from_user', 'to_user', 'amount', 'note', 'date']
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Tutar sıfırdan büyük olmalı.')
        return value

    def validate(self, attrs):
        group = attrs.get('group')
        from_user = attrs.get('from_user')
        to_user = attrs.get('to_user')
        if from_user and to_user and from_user == to_user:
            raise serializers.ValidationError(
                {'to_user': 'Kendi kendine ödeme yapamazsın.'}
            )
        if group and from_user:
            if not group.members.filter(id=from_user.id).exists():
                raise serializers.ValidationError(
                    {'from_user': 'Kullanıcı grubun üyesi olmalı.'}
                )
        return attrs


class GroupSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    members = UserSerializer(many=True, read_only=True)
    expense_count = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ['id', 'name', 'description', 'currency', 'invite_code',
                  'created_by', 'members', 'created_at', 'expense_count', 'total_amount']
        read_only_fields = ['invite_code', 'created_at']

    def get_expense_count(self, obj):
        return obj.expenses.count()

    def get_total_amount(self, obj):
        return str(obj.total_expenses())