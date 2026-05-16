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

    elif split_type == 'exact':
        for user_id, amount in custom_shares.items():
            ExpenseShare.objects.create(
                expense=expense,
                user_id=user_id,
                amount=Decimal(str(amount))
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
    """
    Frankfurter.app üzerinden anlık döviz kurunu çeker.
    Hata durumunda None döner — uygulama çökmez.
    """
    import requests
    if from_currency == to_currency:
        return Decimal('1.00')
    try:
        url = f'https://api.frankfurter.app/latest?from={from_currency}&to={to_currency}'
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = data['rates'].get(to_currency)
        return Decimal(str(rate)) if rate else None
    except Exception:
        return None