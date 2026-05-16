from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Group, Expense, Settlement
from .serializers import GroupSerializer, ExpenseSerializer, SettlementSerializer
from .services import calculate_balances, simplify_debts


class IsMember(permissions.BasePermission):
    """Sadece grubun üyesi erişebilir."""
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'members'):
            return obj.members.filter(id=request.user.id).exists()
        if hasattr(obj, 'group'):
            return obj.group.members.filter(id=request.user.id).exists()
        return False


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Kullanıcının dahil olduğu grupları listeler ve detay verir.
    ReadOnly — sadece GET işlemi. Grup yönetimi web arayüzünden yapılır.
    """
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Group.objects.filter(
            members=self.request.user
        ).prefetch_related('members', 'expenses').distinct()

    @action(detail=True, methods=['get'])
    def balances(self, request, pk=None):
        """GET /api/groups/{id}/balances/ — Grup bakiyelerini döndürür."""
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


class ExpenseViewSet(viewsets.ReadOnlyModelViewSet):
    """Kullanıcının dahil olduğu gruplardaki harcamaları listeler."""
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Expense.objects.filter(
            group__members=self.request.user
        ).select_related('paid_by', 'category', 'group').prefetch_related('shares__user').distinct()


class SettlementViewSet(viewsets.ReadOnlyModelViewSet):
    """Kullanıcının dahil olduğu gruplardaki ödemeleri listeler."""
    serializer_class = SettlementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Settlement.objects.filter(
            group__members=self.request.user
        ).select_related('from_user', 'to_user').distinct()