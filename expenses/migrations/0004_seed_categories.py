from django.db import migrations

def seed_categories(apps, schema_editor):
    Category = apps.get_model('expenses', 'Category')
    categories = [
        {'name': 'Yemek',     'icon': 'ti-tools-kitchen-2', 'color': '#f97316'},
        {'name': 'Market',    'icon': 'ti-shopping-cart',    'color': '#22c55e'},
        {'name': 'Ulaşım',    'icon': 'ti-car',              'color': '#3b82f6'},
        {'name': 'Eğlence',   'icon': 'ti-confetti',         'color': '#a855f7'},
        {'name': 'Kira',      'icon': 'ti-home',             'color': '#ef4444'},
        {'name': 'Fatura',    'icon': 'ti-file-invoice',     'color': '#eab308'},
        {'name': 'Sağlık',    'icon': 'ti-heart',            'color': '#ec4899'},
        {'name': 'Diğer',     'icon': 'ti-dots',             'color': '#6b7280'},
    ]
    for c in categories:
        Category.objects.get_or_create(name=c['name'], defaults=c)

class Migration(migrations.Migration):
    dependencies = [
        ('expenses', '0002_notification'),
    ]
    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]