"""
Vadesi gelen tekrarlayan harcamaları işler.
Cron veya Celery ile günlük çalıştırılır.
Manuel: python manage.py process_recurring
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from expenses.models import RecurringExpense, Expense
from expenses.services import build_expense_shares, create_notifications


class Command(BaseCommand):
    help = 'Vadesi gelen tekrarlayan harcamaları oluşturur.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Gerçekten kaydetmeden ne yapılacağını gösterir.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.now().date()

        due = RecurringExpense.objects.filter(
            is_active=True,
            next_run__lte=today
        ).select_related('group', 'paid_by', 'category', 'created_by')

        if not due.exists():
            self.stdout.write('Vadesi gelen tekrarlayan harcama yok.')
            return

        created = 0
        for rec in due:
            self.stdout.write(f'İşleniyor: {rec.title} — {rec.group.name}')

            if not dry_run:
                expense = Expense.objects.create(
                    group=rec.group,
                    title=rec.title,
                    description=rec.description,
                    amount=rec.amount,
                    paid_by=rec.paid_by,
                    category=rec.category,
                    split_type=rec.split_type,
                    date=today,
                )
                members = list(rec.group.members.all())
                build_expense_shares(expense, rec.split_type, members)
                create_notifications(expense=expense, actor=rec.paid_by)

                # Bir sonraki çalışma tarihini güncelle
                rec.next_run = rec.compute_next_run(rec.next_run)
                rec.save(update_fields=['next_run'])
                created += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(f'Dry-run: {due.count()} harcama oluşturulurdu.')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'{created} tekrarlayan harcama oluşturuldu.')
            )