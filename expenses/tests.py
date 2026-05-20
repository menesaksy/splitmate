from urllib import response

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date

from .models import Category, Group, Membership, Expense, ExpenseShare, Settlement
from .services import calculate_balances, simplify_debts, build_expense_shares, create_notifications


class ModelTests(TestCase):
    """Model davranışları ve constraint testleri."""

    def setUp(self):
        self.user = User.objects.create_user(username='enes', password='test1234')
        self.group = Group.objects.create(name='Ev', created_by=self.user)
        Membership.objects.create(user=self.user, group=self.group, role='admin')

    def test_group_invite_code_auto_generated(self):
        """Grup oluşturulunca davet kodu otomatik üretilmeli."""
        self.assertTrue(self.group.invite_code)
        self.assertGreater(len(self.group.invite_code), 0)

    def test_group_str(self):
        self.assertEqual(str(self.group), 'Ev')

    def test_membership_unique(self):
        """Aynı kullanıcı aynı gruba iki kez üye olamamalı."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Membership.objects.create(user=self.user, group=self.group)

    def test_expense_share_unique(self):
        """Aynı harcamada aynı kullanıcının iki payı olamamalı."""
        from django.db import IntegrityError
        expense = Expense.objects.create(
            group=self.group, title='Test', amount=Decimal('100'),
            paid_by=self.user, date=date.today()
        )
        ExpenseShare.objects.create(expense=expense, user=self.user, amount=Decimal('50'))
        with self.assertRaises(IntegrityError):
            ExpenseShare.objects.create(expense=expense, user=self.user, amount=Decimal('25'))


class BalanceCalculationTests(TestCase):
    """Borç netleştirme algoritmasının doğru çalıştığını test eder."""

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass')
        self.bob = User.objects.create_user(username='bob', password='pass')
        self.carol = User.objects.create_user(username='carol', password='pass')

        self.group = Group.objects.create(name='Trip', created_by=self.alice)
        for u in [self.alice, self.bob, self.carol]:
            Membership.objects.create(user=u, group=self.group)

    def test_simple_equal_split(self):
        """
        Alice 90 TL ödedi, eşit paylaşıldı (her biri 30).
        Alice'in alacağı: +60, Bob: -30, Carol: -30.
        """
        expense = Expense.objects.create(
            group=self.group, title='Yemek', amount=Decimal('90'),
            paid_by=self.alice, date=date.today()
        )
        for u in [self.alice, self.bob, self.carol]:
            ExpenseShare.objects.create(expense=expense, user=u, amount=Decimal('30'))

        balances = calculate_balances(self.group)
        self.assertEqual(balances[self.alice.id], Decimal('60'))
        self.assertEqual(balances[self.bob.id], Decimal('-30'))
        self.assertEqual(balances[self.carol.id], Decimal('-30'))

    def test_simplify_minimizes_transactions(self):
        """
        Alice +60, Bob -30, Carol -30.
        En verimli: Bob → Alice 30, Carol → Alice 30. (2 işlem)
        """
        expense = Expense.objects.create(
            group=self.group, title='Yemek', amount=Decimal('90'),
            paid_by=self.alice, date=date.today()
        )
        for u in [self.alice, self.bob, self.carol]:
            ExpenseShare.objects.create(expense=expense, user=u, amount=Decimal('30'))

        transactions = simplify_debts(self.group)
        self.assertEqual(len(transactions), 2)
        # Tüm transferler Alice'e gitmeli
        for from_id, to_id, amount in transactions:
            self.assertEqual(to_id, self.alice.id)
            self.assertEqual(amount, Decimal('30.00'))

    def test_settlement_reduces_debt(self):
        """
        Bob, Alice'e 30 TL ödedi. Bob'un borcu 0 olmalı.
        """
        expense = Expense.objects.create(
            group=self.group, title='Yemek', amount=Decimal('60'),
            paid_by=self.alice, date=date.today()
        )
        for u in [self.alice, self.bob]:
            ExpenseShare.objects.create(expense=expense, user=u, amount=Decimal('30'))

        # Önce: Bob -30
        balances_before = calculate_balances(self.group)
        self.assertEqual(balances_before[self.bob.id], Decimal('-30'))

        # Bob, Alice'e öder
        Settlement.objects.create(
            group=self.group, from_user=self.bob, to_user=self.alice,
            amount=Decimal('30'), date=date.today()
        )

        balances_after = calculate_balances(self.group)
        self.assertEqual(balances_after[self.bob.id], Decimal('0'))
        self.assertEqual(balances_after[self.alice.id], Decimal('0'))


class ViewAccessTests(TestCase):
    """View erişim ve authorization testleri."""

    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(username='user1', password='pass1234')
        self.user2 = User.objects.create_user(username='user2', password='pass1234')

        self.group = Group.objects.create(name='Gizli', created_by=self.user1)
        Membership.objects.create(user=self.user1, group=self.group, role='admin')

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_works_when_logged_in(self):
        self.client.login(username='user1', password='pass1234')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_non_member_cannot_view_group(self):
        """user2, user1'in grubunu göremez."""
        self.client.login(username='user2', password='pass1234')
        response = self.client.get(reverse('group_detail', args=[self.group.pk]))
        # Yönlendirme veya 403 — handle_no_permission redirect veriyor
        self.assertIn(response.status_code, [302, 403])

    def test_member_can_view_group(self):
        self.client.login(username='user1', password='pass1234')
        response = self.client.get(reverse('group_detail', args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)


class JoinGroupTests(TestCase):
    """Davet kodu ile gruba katılma akışı."""

    def setUp(self):
        self.client = Client()
        self.creator = User.objects.create_user(username='creator', password='pass')
        self.joiner = User.objects.create_user(username='joiner', password='pass')
        self.group = Group.objects.create(name='Ortak', created_by=self.creator)
        Membership.objects.create(user=self.creator, group=self.group, role='admin')

    def test_join_with_valid_code(self):
        self.client.login(username='joiner', password='pass')
        self.client.post(reverse('join_group'), {'invite_code': self.group.invite_code})
        self.assertTrue(
            Membership.objects.filter(user=self.joiner, group=self.group).exists()
        )

    def test_join_with_invalid_code_fails(self):
        self.client.login(username='joiner', password='pass')
        self.client.post(reverse('join_group'), {'invite_code': 'NOTREAL12345'})
        self.assertFalse(
            Membership.objects.filter(user=self.joiner, group=self.group).exists()
        )


class AjaxSettleTests(TestCase):
    """AJAX hızlı ödeme endpoint testleri."""

    def setUp(self):
        self.client = Client()
        self.u1 = User.objects.create_user(username='u1', password='pass')
        self.u2 = User.objects.create_user(username='u2', password='pass')
        self.group = Group.objects.create(name='Test', created_by=self.u1)
        Membership.objects.create(user=self.u1, group=self.group, role='admin')
        Membership.objects.create(user=self.u2, group=self.group)

    def test_quick_settle_creates_settlement(self):
        # u2 kendi adına u1'e ödeme yapıyor (doğru kullanım)
        self.client.login(username='u2', password='pass')
        response = self.client.post(
            reverse('ajax_quick_settle', args=[self.group.pk]),
            {'from_user_id': self.u2.id, 'to_user_id': self.u1.id, 'amount': '50.00'}
       )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'success': True})
        self.assertEqual(Settlement.objects.count(), 1)

    def test_quick_settle_rejects_non_member(self):
        outsider = User.objects.create_user(username='outsider', password='pass')
        self.client.login(username='outsider', password='pass')
        response = self.client.post(
            reverse('ajax_quick_settle', args=[self.group.pk]),
            {'from_user_id': self.u2.id, 'to_user_id': self.u1.id, 'amount': '50.00'}
        )
        self.assertEqual(response.status_code, 403)


class BuildSharesTests(TestCase):
    """build_expense_shares fonksiyonu testleri."""

    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pass')
        self.bob = User.objects.create_user(username='bob', password='pass')
        self.group = Group.objects.create(name='Trip', created_by=self.alice)
        for u in [self.alice, self.bob]:
            Membership.objects.create(user=u, group=self.group)

    def test_equal_split(self):
        expense = Expense.objects.create(
            group=self.group, title='X', amount=Decimal('100'),
            paid_by=self.alice, date=date.today()
        )
        build_expense_shares(expense, 'equal', [self.alice, self.bob])
        shares = expense.shares.all()
        self.assertEqual(shares.count(), 2)
        total = sum(s.amount for s in shares)
        self.assertEqual(total, Decimal('100'))

    def test_percent_split(self):
        expense = Expense.objects.create(
            group=self.group, title='X', amount=Decimal('100'),
            paid_by=self.alice, date=date.today()
        )
        custom = {str(self.alice.id): 30, str(self.bob.id): 70}
        build_expense_shares(expense, 'percent', [self.alice, self.bob], custom)
        shares = {s.user_id: s.amount for s in expense.shares.all()}
        self.assertEqual(shares[self.alice.id], Decimal('30.00'))
        self.assertEqual(shares[self.bob.id], Decimal('70.00'))
    
class ExpenseUpdateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='owner', password='pass')
        self.other = User.objects.create_user(username='other', password='pass')
        self.group = Group.objects.create(name='Test', created_by=self.user)
        Membership.objects.create(user=self.user, group=self.group, role='admin')
        Membership.objects.create(user=self.other, group=self.group)
        self.expense = Expense.objects.create(
            group=self.group, title='Eski başlık',
            amount=Decimal('100'), paid_by=self.user, date=date.today()
        )
        build_expense_shares(self.expense, 'equal', [self.user, self.other])

    def test_owner_can_update(self):
        self.client.login(username='owner', password='pass')
        response = self.client.post(
            reverse('expense_update', args=[self.expense.pk]),
            {
                'title': 'Yeni başlık',
                'amount': '120.00',
                'paid_by': self.user.id,
                'split_type': 'equal',
                'date': date.today().isoformat(),
                'custom_shares_json': '{}',
            }
        )
        self.assertIn(response.status_code, [200, 302])
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.title, 'Yeni başlık')

    def test_non_owner_cannot_update(self):
        self.client.login(username='other', password='pass')
        response = self.client.post(
            reverse('expense_update', args=[self.expense.pk]),
            {'title': 'Hack', 'amount': '999', 'paid_by': self.user.id,
             'split_type': 'equal', 'date': date.today().isoformat()}
        )
        self.assertIn(response.status_code, [302, 403])
        self.expense.refresh_from_db()
        self.assertNotEqual(self.expense.title, 'Hack')

    def test_shares_recalculated_on_update(self):
        self.client.login(username='owner', password='pass')
        self.client.post(
            reverse('expense_update', args=[self.expense.pk]),
            {
                'title': 'Güncellendi',
                'amount': '200.00',
                'paid_by': self.user.id,
                'split_type': 'equal',
                'date': date.today().isoformat(),
                'custom_shares_json': '{}',
            }
        )
        self.expense.refresh_from_db()
        total_shares = sum(s.amount for s in self.expense.shares.all())
        self.assertEqual(total_shares, Decimal('200.00'))

class APITests(TestCase):
    """REST API endpoint testleri."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='apiuser', password='pass1234')
        self.other = User.objects.create_user(username='other', password='pass1234')
        self.group = Group.objects.create(name='API Test', created_by=self.user)
        Membership.objects.create(user=self.user, group=self.group, role='admin')
        Membership.objects.create(user=self.other, group=self.group)

    def test_api_requires_auth(self):
        """Giriş yapmadan API erişilememeli."""
        response = self.client.get('/api/groups/')
        self.assertIn(response.status_code, [401, 403])

    def test_api_returns_own_groups(self):
        """Kullanıcı sadece kendi gruplarını görür."""
        # Başka bir kullanıcının grubu
        other_group = Group.objects.create(name='Yabancı', created_by=self.other)
        Membership.objects.create(user=self.other, group=other_group, role='admin')

        self.client.login(username='apiuser', password='pass1234')
        response = self.client.get('/api/groups/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        names = [g['name'] for g in results]
        self.assertIn('API Test', names)
        self.assertNotIn('Yabancı', names)

    def test_api_group_balances_endpoint(self):
        """Bakiye endpoint'i çalışıyor mu?"""
        self.client.login(username='apiuser', password='pass1234')
        response = self.client.get(f'/api/groups/{self.group.pk}/balances/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('balances', data)
        self.assertIn('suggested_payments', data)

    def test_api_expenses_returns_only_member_expenses(self):
        """API sadece üyenin grubundaki harcamaları döndürür."""
        Expense.objects.create(
            group=self.group, title='Ortak Harcama',
            amount=Decimal('100'), paid_by=self.user, date=date.today()
        )
        # Başka gruba harcama
        other_group = Group.objects.create(name='Gizli', created_by=self.other)
        Membership.objects.create(user=self.other, group=other_group, role='admin')
        Expense.objects.create(
            group=other_group, title='Gizli Harcama',
            amount=Decimal('50'), paid_by=self.other, date=date.today()
        )

        self.client.login(username='apiuser', password='pass1234')
        response = self.client.get('/api/expenses/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data)
        titles = [e['title'] for e in results]
        self.assertIn('Ortak Harcama', titles)
        self.assertNotIn('Gizli Harcama', titles)

class JWTAuthTests(TestCase):
    """JWT authentication testleri."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='jwtuser', password='pass1234')
        self.group = Group.objects.create(name='JWT Test', created_by=self.user)
        Membership.objects.create(user=self.user, group=self.group, role='admin')

    def test_obtain_token(self):
        """Geçerli credentials ile token alınabilmeli."""
        response = self.client.post('/api/token/', {
            'username': 'jwtuser',
            'password': 'pass1234',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('access', data)
        self.assertIn('refresh', data)

    def test_access_api_with_token(self):
        """JWT token ile API'ye erişilebilmeli."""
        # Token al
        resp = self.client.post('/api/token/', {
            'username': 'jwtuser',
            'password': 'pass1234',
        }, content_type='application/json')
        token = resp.json()['access']

        # Token ile istek yap
        response = self.client.get(
            '/api/groups/',
            HTTP_AUTHORIZATION=f'Bearer {token}'
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_token_rejected(self):
        """Geçersiz token reddedilmeli."""
        response = self.client.get(
            '/api/groups/',
            HTTP_AUTHORIZATION='Bearer invalidtoken123'
        )
        self.assertEqual(response.status_code, 401)

    def test_refresh_token(self):
        """Refresh token ile yeni access token alınabilmeli."""
        resp = self.client.post('/api/token/', {
            'username': 'jwtuser',
            'password': 'pass1234',
        }, content_type='application/json')
        refresh = resp.json()['refresh']

        response = self.client.post('/api/token/refresh/', {
            'refresh': refresh,
        }, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.json())

    def test_wrong_password_rejected(self):
        """Yanlış şifre ile token alınamamalı."""
        response = self.client.post('/api/token/', {
            'username': 'jwtuser',
            'password': 'yanlis',
        }, content_type='application/json')
        self.assertEqual(response.status_code, 401)

class EmailNotificationTests(TestCase):
    """Email bildirim testleri."""

    def setUp(self):
        self.actor = User.objects.create_user(
            username='actor', password='pass', email='actor@test.com'
        )
        self.member = User.objects.create_user(
            username='member', password='pass', email='member@test.com'
        )
        self.no_email_member = User.objects.create_user(
            username='noemail', password='pass', email=''
        )
        self.group = Group.objects.create(name='Email Test', created_by=self.actor)
        for u in [self.actor, self.member, self.no_email_member]:
            Membership.objects.create(user=u, group=self.group)

    def test_expense_email_sent(self):
        """Harcama eklenince üyelere email gitmeli."""
        from django.core import mail
        expense = Expense.objects.create(
            group=self.group, title='Test Harcama',
            amount=Decimal('90'), paid_by=self.actor, date=date.today()
        )
        create_notifications(expense=expense, actor=self.actor)
        # actor hariç 2 üye var ama sadece email'i olanlar alır
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['member@test.com'])
        self.assertIn('Test Harcama', mail.outbox[0].body)

    def test_settlement_email_sent(self):
        """Ödeme eklenince email gitmeli."""
        from django.core import mail
        settlement = Settlement.objects.create(
            group=self.group, from_user=self.member,
            to_user=self.actor, amount=Decimal('30'), date=date.today()
        )
        create_notifications(settlement=settlement, actor=self.member)
        self.assertEqual(len(mail.outbox), 1)

    def test_no_email_user_skipped(self):
        """Email adresi olmayan kullanıcı atlanmalı."""
        from django.core import mail
        expense = Expense.objects.create(
            group=self.group, title='Skip Test',
            amount=Decimal('60'), paid_by=self.actor, date=date.today()
        )
        create_notifications(expense=expense, actor=self.actor)
        recipients = [m.to[0] for m in mail.outbox]
        self.assertNotIn('', recipients)

    def test_group_join_email_sent(self):
        """Gruba katılımda email gitmeli."""
        from django.core import mail
        new_user = User.objects.create_user(
            username='newuser', password='pass', email='new@test.com'
        )
        Membership.objects.create(user=new_user, group=self.group)
        create_notifications(group=self.group, actor=new_user)
        self.assertGreater(len(mail.outbox), 0)

class RateLimitTests(TestCase):
    """Rate limiting testleri."""

    def setUp(self):
        self.client = Client()
        from django.core.cache import cache
        cache.clear()

    def test_signup_rate_limit(self):
        """5 denemeden sonra signup 429 dönmeli."""
        for i in range(5):
            self.client.post('/signup/', {
                'username': f'user{i}',
                'password1': 'Deneme1234!',
                'password2': 'Deneme1234!',
            })
        response = self.client.post('/signup/', {
            'username': 'blocked',
            'password1': 'Deneme1234!',
            'password2': 'Deneme1234!',
        })
        self.assertEqual(response.status_code, 429)

    def test_join_group_rate_limit(self):
        """10 denemeden sonra join_group 429 dönmeli."""
        user = User.objects.create_user(username='rltestuser', password='pass1234')
        self.client.login(username='rltestuser', password='pass1234')
        for i in range(10):
            self.client.post('/groups/join/', {'invite_code': f'FAKE{i:08d}'})
        response = self.client.post('/groups/join/', {'invite_code': 'BLOCKED123'})
        self.assertEqual(response.status_code, 429)

    def test_get_requests_not_limited(self):
        """GET istekleri rate limit'e takılmamalı."""
        from django.core.cache import cache
        cache.clear()
        for _ in range(20):
            response = self.client.get('/signup/')
        self.assertEqual(response.status_code, 200)

    def test_different_ips_independent(self):
        """Farklı IP'ler birbirinden bağımsız sayılmalı."""
        from django.core.cache import cache
        cache.clear()
        for i in range(5):
            self.client.post('/signup/', {
                'username': f'ip1user{i}',
                'password1': 'Deneme1234!',
                'password2': 'Deneme1234!',
            }, HTTP_X_FORWARDED_FOR='1.2.3.4')
        response = self.client.post('/signup/', {
            'username': 'ip2user',
            'password1': 'Deneme1234!',
            'password2': 'Deneme1234!',
        }, HTTP_X_FORWARDED_FOR='5.6.7.8')
        self.assertNotEqual(response.status_code, 429)

class RecurringExpenseTests(TestCase):
    """Tekrarlayan harcama testleri."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='recuser', password='pass1234')
        self.group = Group.objects.create(name='Rec Test', created_by=self.user)
        Membership.objects.create(user=self.user, group=self.group, role='admin')

    def test_create_recurring_expense(self):
        """Tekrarlayan harcama oluşturulabilmeli."""
        from expenses.models import RecurringExpense
        rec = RecurringExpense.objects.create(
            group=self.group,
            title='Kira',
            amount=Decimal('1500'),
            paid_by=self.user,
            split_type='equal',
            frequency='monthly',
            start_date=date.today(),
            next_run=date.today(),
            created_by=self.user,
        )
        self.assertEqual(str(rec), f'Kira (Aylık) — Rec Test')

    def test_compute_next_run_monthly(self):
        """Aylık sonraki tarih doğru hesaplanmalı."""
        from expenses.models import RecurringExpense
        from datetime import date as d
        rec = RecurringExpense(frequency='monthly')
        result = rec.compute_next_run(d(2024, 1, 15))
        self.assertEqual(result, d(2024, 2, 15))

    def test_compute_next_run_weekly(self):
        """Haftalık sonraki tarih doğru hesaplanmalı."""
        from expenses.models import RecurringExpense
        from datetime import date as d
        rec = RecurringExpense(frequency='weekly')
        result = rec.compute_next_run(d(2024, 1, 15))
        self.assertEqual(result, d(2024, 1, 22))

    def test_management_command_creates_expense(self):
        """process_recurring komutu vadesi gelen harcamayı oluşturmalı."""
        from expenses.models import RecurringExpense
        from django.core.management import call_command
        from datetime import date as d

        rec = RecurringExpense.objects.create(
            group=self.group,
            title='Fatura',
            amount=Decimal('200'),
            paid_by=self.user,
            split_type='equal',
            frequency='monthly',
            start_date=d(2024, 1, 1),
            next_run=d(2024, 1, 1),  # Geçmiş tarih — vadesi gelmiş
            created_by=self.user,
        )

        call_command('process_recurring', verbosity=0)

        self.assertEqual(Expense.objects.filter(title='Fatura').count(), 1)
        rec.refresh_from_db()
        # next_run bir ay ilerlemiş olmalı
        self.assertGreater(rec.next_run, d(2024, 1, 1))

    def test_management_command_dry_run(self):
        """Dry-run modunda harcama oluşturulmamalı."""
        from expenses.models import RecurringExpense
        from django.core.management import call_command
        from datetime import date as d

        RecurringExpense.objects.create(
            group=self.group,
            title='Dry Fatura',
            amount=Decimal('100'),
            paid_by=self.user,
            split_type='equal',
            frequency='monthly',
            start_date=d(2024, 1, 1),
            next_run=d(2024, 1, 1),
            created_by=self.user,
        )

        call_command('process_recurring', '--dry-run', verbosity=0)
        self.assertEqual(Expense.objects.filter(title='Dry Fatura').count(), 0)