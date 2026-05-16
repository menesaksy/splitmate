from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),

    path('groups/', views.GroupListView.as_view(), name='group_list'),
    path('groups/new/', views.GroupCreateView.as_view(), name='group_create'),
    path('groups/join/', views.join_group, name='join_group'),
    path('groups/<int:pk>/', views.GroupDetailView.as_view(), name='group_detail'),
    path('groups/<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_update'),
    path('groups/<int:pk>/delete/', views.GroupDeleteView.as_view(), name='group_delete'),

    path('groups/<int:group_pk>/expense/new/', views.ExpenseCreateView.as_view(), name='expense_create'),
    path('expense/<int:pk>/', views.ExpenseDetailView.as_view(), name='expense_detail'),
    path('expense/<int:pk>/delete/', views.ExpenseDeleteView.as_view(), name='expense_delete'),

    path('groups/<int:group_pk>/settle/', views.SettlementCreateView.as_view(), name='settlement_create'),
    path('groups/<int:group_pk>/quick-settle/', views.ajax_quick_settle, name='ajax_quick_settle'),

    path('signup/', views.signup, name='signup'),
]