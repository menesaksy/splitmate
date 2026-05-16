from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
)
from decimal import Decimal
import json

from .models import Group, Membership, Expense, ExpenseShare, Settlement, Category
from .forms import GroupForm, ExpenseForm, SettlementForm, JoinGroupForm
from .services import calculate_balances, simplify_debts, build_expense_shares


# ---------- Auth ----------

def signup(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Hoş geldin! Hadi bir grup oluştur veya katıl.')
            return redirect('group_list')
    else:
        form = UserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})


# ---------- Dashboard ----------

class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expenses/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # Kullanıcının dahil olduğu gruplar
        groups = Group.objects.filter(members=user, is_active=True).distinct()

        # Toplam alacak/borç (tüm grupları gez)
        total_owed_to_me = Decimal('0.00')
        total_i_owe = Decimal('0.00')

        for g in groups:
            balances = calculate_balances(g)
            my_balance = balances.get(user.id, Decimal('0.00'))
            if my_balance > 0:
                total_owed_to_me += my_balance
            elif my_balance < 0:
                total_i_owe += -my_balance

        # Son harcamalar
        recent_expenses = Expense.objects.filter(
            group__in=groups
        ).select_related('group', 'paid_by', 'category')[:10]

        ctx.update({
            'groups': groups,
            'total_owed_to_me': total_owed_to_me,
            'total_i_owe': total_i_owe,
            'net_balance': total_owed_to_me - total_i_owe,
            'recent_expenses': recent_expenses,
        })
        return ctx


# ---------- Grup CRUD ----------

class GroupListView(LoginRequiredMixin, ListView):
    template_name = 'expenses/group_list.html'
    context_object_name = 'groups'

    def get_queryset(self):
        return Group.objects.filter(
            members=self.request.user
        ).annotate(
            expense_count=Count('expenses'),
            total_amount=Sum('expenses__amount')
        ).distinct()


class GroupDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Group
    template_name = 'expenses/group_detail.html'
    context_object_name = 'group'
    paginate_by = 10

    def test_func(self):
        group = self.get_object()
        return group.members.filter(id=self.request.user.id).exists()

    def handle_no_permission(self):
        messages.error(self.request, 'Bu grubun üyesi değilsin.')
        return redirect('group_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        group = self.object

        # Harcama listesi + filtreler
        expenses = group.expenses.select_related('paid_by', 'category').prefetch_related('shares')

        category_id = self.request.GET.get('category')
        if category_id:
            expenses = expenses.filter(category_id=category_id)

        query = self.request.GET.get('q', '').strip()
        if query:
            expenses = expenses.filter(
                Q(title__icontains=query) | Q(description__icontains=query)
            )

        # Bakiyeler ve netleştirme
        balances = calculate_balances(group)
        simplified = simplify_debts(group)

        # User ID → User dönüşümü kolaylaştırmak için
        user_map = {u.id: u for u in group.members.all()}

        balances_display = [
            {'user': user_map[uid], 'amount': amt}
            for uid, amt in balances.items() if uid in user_map
        ]
        balances_display.sort(key=lambda x: x['amount'], reverse=True)

        simplified_display = [
            {
                'from_user': user_map[fid],
                'to_user': user_map[tid],
                'amount': amt
            }
            for fid, tid, amt in simplified
            if fid in user_map and tid in user_map
        ]

        ctx.update({
            'expenses': expenses,
            'balances': balances_display,
            'simplified': simplified_display,
            'categories': Category.objects.all(),
            'query': query,
            'active_category': category_id or '',
            'total_amount': group.total_expenses(),
        })
        return ctx


class GroupCreateView(LoginRequiredMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = 'expenses/group_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        # Oluşturucuyu admin üye yap
        Membership.objects.create(
            user=self.request.user,
            group=self.object,
            role='admin'
        )
        messages.success(self.request, f'"{self.object.name}" grubu oluşturuldu.')
        return response


class GroupUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = 'expenses/group_form.html'

    def test_func(self):
        group = self.get_object()
        return Membership.objects.filter(
            user=self.request.user, group=group, role='admin'
        ).exists()


class GroupDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Group
    template_name = 'expenses/group_confirm_delete.html'
    success_url = reverse_lazy('group_list')

    def test_func(self):
        return self.get_object().created_by == self.request.user


@login_required
def join_group(request):
    """Davet kodu ile gruba katılma."""
    if request.method == 'POST':
        form = JoinGroupForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['invite_code'].strip()
            try:
                group = Group.objects.get(invite_code=code)
            except Group.DoesNotExist:
                messages.error(request, 'Geçersiz davet kodu.')
                return redirect('join_group')

            if Membership.objects.filter(user=request.user, group=group).exists():
                messages.info(request, 'Zaten bu grubun üyesisin.')
            else:
                Membership.objects.create(user=request.user, group=group)
                messages.success(request, f'"{group.name}" grubuna katıldın.')
            return redirect('group_detail', pk=group.pk)
    else:
        form = JoinGroupForm()
    return render(request, 'expenses/join_group.html', {'form': form})


# ---------- Harcama CRUD ----------

class ExpenseCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'expenses/expense_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.group = get_object_or_404(Group, pk=kwargs['group_pk'])
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return self.group.members.filter(id=self.request.user.id).exists()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['group'] = self.group
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['group'] = self.group
        ctx['members'] = self.group.members.all()
        return ctx

    def form_valid(self, form):
        form.instance.group = self.group
        response = super().form_valid(form)

        # Paylaşımları oluştur
        members = list(self.group.members.all())
        split_type = form.cleaned_data['split_type']

        custom = None
        if split_type in ('exact', 'percent'):
            raw = self.request.POST.get('custom_shares_json', '{}')
            try:
                custom = json.loads(raw)
            except json.JSONDecodeError:
                custom = {}

        build_expense_shares(self.object, split_type, members, custom)
        messages.success(self.request, 'Harcama eklendi.')
        return response

    def get_success_url(self):
        return reverse_lazy('group_detail', kwargs={'pk': self.group.pk})


class ExpenseDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    model = Expense
    template_name = 'expenses/expense_detail.html'
    context_object_name = 'expense'

    def test_func(self):
        return self.get_object().group.members.filter(id=self.request.user.id).exists()


class ExpenseDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Expense
    template_name = 'expenses/expense_confirm_delete.html'

    def test_func(self):
        exp = self.get_object()
        return exp.paid_by == self.request.user or \
               Membership.objects.filter(
                   user=self.request.user, group=exp.group, role='admin'
               ).exists()

    def get_success_url(self):
        return reverse_lazy('group_detail', kwargs={'pk': self.object.group.pk})


# ---------- Settlement (ödeme) ----------

class SettlementCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Settlement
    form_class = SettlementForm
    template_name = 'expenses/settlement_form.html'

    def dispatch(self, request, *args, **kwargs):
        self.group = get_object_or_404(Group, pk=kwargs['group_pk'])
        return super().dispatch(request, *args, **kwargs)

    def test_func(self):
        return self.group.members.filter(id=self.request.user.id).exists()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['group'] = self.group
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['group'] = self.group
        return ctx

    def form_valid(self, form):
        form.instance.group = self.group
        messages.success(self.request, 'Ödeme kaydedildi.')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('group_detail', kwargs={'pk': self.group.pk})


# ---------- AJAX endpoints ----------

@login_required
@require_POST
def ajax_quick_settle(request, group_pk):
    """Bir borç ilişkisini tek tıkla 'ödendi' olarak işaretle (AJAX)."""
    group = get_object_or_404(Group, pk=group_pk)
    if not group.members.filter(id=request.user.id).exists():
        return JsonResponse({'error': 'Yetkisiz'}, status=403)

    from_user_id = request.POST.get('from_user_id')
    to_user_id = request.POST.get('to_user_id')
    amount = request.POST.get('amount')

    try:
        from django.contrib.auth.models import User
        from django.utils import timezone
        Settlement.objects.create(
            group=group,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            amount=Decimal(str(amount)),
            date=timezone.now().date(),
            note='Hızlı ödeme'
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)