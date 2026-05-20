from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from decimal import Decimal


class Category(models.Model):
    """Harcama kategorileri (Yemek, Ulaşım, Eğlence vs.)"""
    name = models.CharField(max_length=50, unique=True)
    icon = models.CharField(max_length=30, blank=True, help_text="Bootstrap icon adı, örn: bi-cup-hot")
    color = models.CharField(max_length=20, default='#6c757d', help_text="Hex renk kodu")

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class Group(models.Model):
    """Harcama paylaşan kullanıcı grupları (ev arkadaşları, gezi grubu vs.)"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_groups'
    )
    members = models.ManyToManyField(
        User,
        through='Membership',
        related_name='expense_groups'
    )
    invite_code = models.CharField(max_length=12, unique=True, blank=True)
    currency = models.CharField(max_length=3, default='TRY')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Davet kodu otomatik üret
        if not self.invite_code:
            import secrets
            self.invite_code = secrets.token_urlsafe(8)[:12]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('group_detail', kwargs={'pk': self.pk})

    def total_expenses(self):
        """Bu grupta yapılan toplam harcama"""
        return sum(e.amount for e in self.expenses.all()) or Decimal('0.00')


class Membership(models.Model):
    """Kullanıcı–Grup ara tablosu, rol bilgisi taşır."""
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Üye'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'group']
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user.username} → {self.group.name} ({self.role})"


class Expense(models.Model):
    """Bir harcama: kim ödedi, ne kadar, hangi grupta, kime düşüyor."""
    SPLIT_CHOICES = [
        ('equal', 'Eşit Paylaş'),
        ('exact', 'Birebir Tutar'),
        ('percent', 'Yüzdelik'),
    ]

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='expenses')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='expenses_paid'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expenses'
    )
    split_type = models.CharField(max_length=10, choices=SPLIT_CHOICES, default='equal')
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.amount} {self.group.currency})"

    def get_absolute_url(self):
        return reverse('expense_detail', kwargs={'pk': self.pk})


class ExpenseShare(models.Model):
    """Bir harcamadaki kişi başı paylaşım: kim ne kadar borçlu."""
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expense_shares')
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ['expense', 'user']

    def __str__(self):
        return f"{self.user.username}: {self.amount}"


class Settlement(models.Model):
    """Bir kullanıcıdan diğerine yapılan ödeme (borç kapatma)."""
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='settlements')
    from_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='settlements_paid'
    )
    to_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='settlements_received'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.from_user.username} → {self.to_user.username}: {self.amount}"
    
class Notification(models.Model):
    TYPE_CHOICES = [
        ('expense', 'Yeni Harcama'),
        ('settlement', 'Ödeme'),
        ('group_join', 'Gruba Katılım'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications'
    )
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    group = models.ForeignKey(
        'Group', on_delete=models.CASCADE, null=True, blank=True
    )
    expense = models.ForeignKey(
        'Expense', on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.title}"
    
