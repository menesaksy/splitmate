#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate

# Superuser otomatik oluştur (yoksa)
python manage.py shell << 'EOF'
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@splitmate.com', 'admin1234')
    print("Superuser oluşturuldu: admin / admin1234")
else:
    print("Superuser zaten var.")
EOF