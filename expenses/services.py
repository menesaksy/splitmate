"""
SplitMate'in borç netleştirme motoru.

Bu modül, bir gruptaki tüm harcama ve ödemeleri analiz edip
'kim kime ne kadar borçlu' sorusunu minimum transfer sayısıyla cevaplar.

Algoritma: Minimum Cash Flow (Greedy)
- Her kullanıcının net bakiyesi hesaplanır (alacaklı/borçlu).
- En çok alacaklı ile en çok borçlu eşleştirilir, biri sıfırlanana kadar.
- Bu işlem tüm bakiyeler sıfır olana dek tekrar eder.
- Sonuç: N kişi için en fazla N-1 transfer (optimum).
"""

from collections import defaultdict
from decimal import Decimal


def calculate_balances(group):
    """
    Bir gruptaki herkesin net bakiyesini hesaplar.
    Pozitif → alacaklı (ona borç var)
    Negatif → borçlu (o ödeyecek)
    """
    balances = defaultdict(lambda: Decimal('0.00'))

    # Harcamalar: ödeyen +, paya düşenler -
    for expense in group.expenses.prefetch_related('shares__user').all():
        balances[expense.paid_by_id] += expense.amount
        for share in expense.shares.all():
            balances[share.user_id] -= share.amount

    # Ödemeler (Settlement): ödeyen +'ya gider (borcu azaldı), alan -'ye (alacağı azaldı)
    for s in group.settlements.all():
        balances[s.from_user_id] += s.amount
        balances[s.to_user_id] -= s.amount

    return dict(balances)


def simplify_debts(group):
    """
    Net bakiyeleri minimum transfer sayısıyla netleştirir.
    Dönüş: [(from_user_id, to_user_id, amount), ...]
    """
    balances = calculate_balances(group)

    # Yuvarlama hatalarını yutmak için 0.01'den küçükleri at
    creditors = [(uid, amt) for uid, amt in balances.items() if amt > Decimal('0.01')]
    debtors = [(uid, -amt) for uid, amt in balances.items() if amt < Decimal('-0.01')]

    # Büyükten küçüğe sırala
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    transactions = []
    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        debtor_id, debt = debtors[i]
        creditor_id, credit = creditors[j]

        # İki tarafın minimum miktarı transfer edilir
        transfer = min(debt, credit)
        transactions.append((debtor_id, creditor_id, transfer.quantize(Decimal('0.01'))))

        # Kalan bakiyeleri güncelle
        debt -= transfer
        credit -= transfer

        if debt < Decimal('0.01'):
            i += 1
        else:
            debtors[i] = (debtor_id, debt)

        if credit < Decimal('0.01'):
            j += 1
        else:
            creditors[j] = (creditor_id, credit)

    return transactions


def build_expense_shares(expense, split_type, members, custom_shares=None):
    """
    Bir harcama için ExpenseShare kayıtlarını üretir.

    split_type:
      - 'equal': eşit böl
      - 'exact': custom_shares = {user_id: amount}
      - 'percent': custom_shares = {user_id: percentage}
    """
    from .models import ExpenseShare

    if split_type == 'equal':
        per_person = (expense.amount / len(members)).quantize(Decimal('0.01'))
        # Yuvarlama artığını ilk kişiye ekle
        total_assigned = per_person * len(members)
        remainder = expense.amount - total_assigned

        for idx, user in enumerate(members):
            amount = per_person + (remainder if idx == 0 else Decimal('0.00'))
            ExpenseShare.objects.create(expense=expense, user=user, amount=amount)

    elif split_type == 'percent':
        total_pct = sum(Decimal(str(pct)) for pct in custom_shares.values())
        if abs(total_pct - Decimal('100')) > Decimal('0.01'):
            raise ValueError(f'Yüzdelerin toplamı 100 olmalı, şu an: {total_pct}')
        for user_id, pct in custom_shares.items():
            amount = (expense.amount * Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.01'))
            ExpenseShare.objects.create(
                expense=expense,
                user_id=user_id,
                amount=amount
            )

    elif split_type == 'percent':
        for user_id, pct in custom_shares.items():
            amount = (expense.amount * Decimal(str(pct)) / Decimal('100')).quantize(Decimal('0.01'))
            ExpenseShare.objects.create(
                expense=expense,
                user_id=user_id,
                amount=amount
            ) 

def get_exchange_rate(from_currency, to_currency='TRY'):
    from django.core.cache import cache
    import requests

    if from_currency == to_currency:
        return Decimal('1.00')

    cache_key = f'exchange_rate_{from_currency}_{to_currency}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        url = f'https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}'
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = data['rates'].get(to_currency)
        if rate:
            result = Decimal(str(rate))
            cache.set(cache_key, result, timeout=3600)  # 1 saat cache
            return result
        return None
    except Exception:
        return None
    
def send_email_notification(user, subject, message, html_message=None):
    """
    Kullanıcıya email gönderir.
    Email adresi yoksa veya hata olursa sessizce geçer.
    """
    from django.core.mail import send_mail
    from django.conf import settings

    if not user.email:
        return
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=True,
        )
    except Exception:
        pass


def _build_expense_email(actor, expense):
    """Harcama bildirimi için düz metin ve HTML içerik üretir."""
    from django.conf import settings
    url = f"{settings.FRONTEND_URL}/expense/{expense.pk}/"
    plain = (
        f"Merhaba,\n\n"
        f"{actor.username} grubunuza yeni bir harcama ekledi.\n\n"
        f"Harcama: {expense.title}\n"
        f"Tutar: {expense.amount} {expense.group.currency}\n"
        f"Grup: {expense.group.name}\n\n"
        f"Detaylar için: {url}\n\n"
        f"SplitMate"
    )
    html = (
        f"<p>Merhaba,</p>"
        f"<p><strong>{actor.username}</strong> grubunuza yeni bir harcama ekledi.</p>"
        f"<table>"
        f"<tr><td><strong>Harcama:</strong></td><td>{expense.title}</td></tr>"
        f"<tr><td><strong>Tutar:</strong></td><td>{expense.amount} {expense.group.currency}</td></tr>"
        f"<tr><td><strong>Grup:</strong></td><td>{expense.group.name}</td></tr>"
        f"</table>"
        f"<p><a href='{url}'>Detayları görüntüle</a></p>"
        f"<p>SplitMate</p>"
    )
    return plain, html


def _build_settlement_email(actor, settlement):
    """Ödeme bildirimi için düz metin ve HTML içerik üretir."""
    from django.conf import settings
    url = f"{settings.FRONTEND_URL}/groups/{settlement.group.pk}/"
    plain = (
        f"Merhaba,\n\n"
        f"{actor.username} bir ödeme kaydetti.\n\n"
        f"Tutar: {settlement.amount} {settlement.group.currency}\n"
        f"Grup: {settlement.group.name}\n\n"
        f"Detaylar için: {url}\n\n"
        f"SplitMate"
    )
    html = (
        f"<p>Merhaba,</p>"
        f"<p><strong>{actor.username}</strong> bir ödeme kaydetti.</p>"
        f"<table>"
        f"<tr><td><strong>Tutar:</strong></td><td>{settlement.amount} {settlement.group.currency}</td></tr>"
        f"<tr><td><strong>Grup:</strong></td><td>{settlement.group.name}</td></tr>"
        f"</table>"
        f"<p><a href='{url}'>Grubu görüntüle</a></p>"
        f"<p>SplitMate</p>"
    )
    return plain, html


def _build_group_join_email(actor, group):
    """Gruba katılım bildirimi için içerik üretir."""
    from django.conf import settings
    url = f"{settings.FRONTEND_URL}/groups/{group.pk}/"
    plain = (
        f"Merhaba,\n\n"
        f"{actor.username} '{group.name}' grubuna katıldı.\n\n"
        f"Detaylar için: {url}\n\n"
        f"SplitMate"
    )
    html = (
        f"<p>Merhaba,</p>"
        f"<p><strong>{actor.username}</strong> grubunuza katıldı.</p>"
        f"<p><strong>Grup:</strong> {group.name}</p>"
        f"<p><a href='{url}'>Grubu görüntüle</a></p>"
        f"<p>SplitMate</p>"
    )
    return plain, html


def create_notifications(expense=None, settlement=None, group=None, actor=None):
    """Harcama veya ödeme eklenince grup üyelerine bildirim gönder."""
    from .models import Notification

    if expense:
        members = expense.group.members.exclude(id=actor.id)
        plain, html = _build_expense_email(actor, expense)
        for member in members:
            Notification.objects.create(
                user=member,
                notification_type='expense',
                title=f'{actor.username} yeni harcama ekledi',
                message=f'"{expense.title}" — {expense.amount} {expense.group.currency}',
                group=expense.group,
                expense=expense,
            )
            send_email_notification(
                user=member,
                subject=f'[SplitMate] {actor.username} yeni harcama ekledi',
                message=plain,
                html_message=html,
            )

    if settlement:
        members = settlement.group.members.exclude(id=actor.id)
        plain, html = _build_settlement_email(actor, settlement)
        for member in members:
            Notification.objects.create(
                user=member,
                notification_type='settlement',
                title=f'{actor.username} ödeme kaydetti',
                message=f'{settlement.amount} {settlement.group.currency} ödeme yapıldı',
                group=settlement.group,
            )
            send_email_notification(
                user=member,
                subject=f'[SplitMate] {actor.username} ödeme kaydetti',
                message=plain,
                html_message=html,
            )

    if group and actor:
        members = group.members.exclude(id=actor.id)
        plain, html = _build_group_join_email(actor, group)
        for member in members:
            Notification.objects.create(
                user=member,
                notification_type='group_join',
                title=f'{actor.username} gruba katıldı',
                message=f'"{group.name}" grubuna yeni üye katıldı',
                group=group,
            )
            send_email_notification(
                user=member,
                subject=f'[SplitMate] {actor.username} grubunuza katıldı',
                message=plain,
                html_message=html,
            )