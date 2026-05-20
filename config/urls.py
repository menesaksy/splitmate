from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from expenses.api import GroupViewSet, ExpenseViewSet, SettlementViewSet
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

router = DefaultRouter()
router.register(r'groups', GroupViewSet, basename='api-group')
router.register(r'expenses', ExpenseViewSet, basename='api-expense')
router.register(r'settlements', SettlementViewSet, basename='api-settlement')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('api/', include(router.urls)),
    path('api-auth/', include('rest_framework.urls')),
    # JWT endpoint'leri
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('', include('expenses.urls')),
]