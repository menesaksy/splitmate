from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Group, Expense, Settlement
from .serializers import (
    GroupSerializer,
    ExpenseSerializer, ExpenseWriteSerializer,
    SettlementSerializer, SettlementWriteSerializer,
)
from .services import calculate_balances, simplify_debts, build_expense_shares, create_notifications


class IsMember(permissions.BasePermission):
    """Sadece grubun üyesi erişebilir."""
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'members'):
            return obj.members.filter(id=request.user.id).exists()
        if hasattr(obj, 'group'):
            return obj.group.members.filter(id=request.user.id).exists()
        return False


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Group.objects.filter(
            members=self.request.user
        ).prefetch_related('members', 'expenses').distinct()

    @action(detail=True, methods=['get'])
    def balances(self, request, pk=None):
        """GET /api/groups/{id}/balances/"""
        group = self.get_object()
        if not group.members.filter(id=request.user.id).exists():
            return Response({'error': 'Yetkisiz'}, status=403)

        raw = calculate_balances(group)
        simplified = simplify_debts(group)
        user_map = {u.id: u.username for u in group.members.all()}

        return Response({
            'group': group.name,
            'currency': group.currency,
            'balances': [
                {'user': user_map.get(uid, uid), 'amount': str(amt)}
                for uid, amt in raw.items()
            ],
            'suggested_payments': [
                {
                    'from': user_map.get(fid, fid),
                    'to': user_map.get(tid, tid),
                    'amount': str(amt)
                }
                for fid, tid, amt in simplified
            ]
        })


class ExpenseViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsMember]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return ExpenseWriteSerializer
        return ExpenseSerializer

    def get_queryset(self):
        return Expense.objects.filter(
            group__members=self.request.user
        ).select_related('paid_by', 'category', 'group').prefetch_related('shares__user').distinct()

    def perform_create(self, serializer):
        expense = serializer.save()
        members = list(expense.group.members.all())
        build_expense_shares(expense, expense.split_type, members)
        create_notifications(expense=expense, actor=self.request.user)

    def perform_update(self, serializer):
        expense = serializer.save()
        # Payları sil, yeniden hesapla
        expense.shares.all().delete()
        members = list(expense.group.members.all())
        build_expense_shares(expense, expense.split_type, members)

    def destroy(self, request, *args, **kwargs):
        expense = self.get_object()
        # Sadece ödeyen veya grup admini silebilir
        is_payer = expense.paid_by == request.user
        is_admin = expense.group.membership_set.filter(
            user=request.user, role='admin'
        ).exists()
        if not (is_payer or is_admin):
            return Response(
                {'error': 'Sadece harcamayı ekleyen veya grup admini silebilir.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)


class SettlementViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsMember]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return SettlementWriteSerializer
        return SettlementSerializer

    def get_queryset(self):
        return Settlement.objects.filter(
            group__members=self.request.user
        ).select_related('from_user', 'to_user', 'group').distinct()

    def perform_create(self, serializer):
        settlement = serializer.save()
        create_notifications(settlement=settlement, actor=self.request.user)

    def destroy(self, request, *args, **kwargs):
        settlement = self.get_object()
        # Sadece from_user veya grup admini silebilir
        is_owner = settlement.from_user == request.user
        is_admin = settlement.group.membership_set.filter(
            user=request.user, role='admin'
        ).exists()
        if not (is_owner or is_admin):
            return Response(
                {'error': 'Sadece ödemeyi yapan veya grup admini silebilir.'},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)