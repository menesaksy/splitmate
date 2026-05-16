from django.contrib import admin
from .models import Category, Group, Membership, Expense, ExpenseShare, Settlement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon', 'color']


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 1


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'currency', 'created_at', 'is_active']
    list_filter = ['is_active', 'currency', 'created_at']
    search_fields = ['name', 'description']
    inlines = [MembershipInline]


class ExpenseShareInline(admin.TabularInline):
    model = ExpenseShare
    extra = 1


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ['title', 'amount', 'group', 'paid_by', 'category', 'date']
    list_filter = ['group', 'category', 'split_type', 'date']
    search_fields = ['title', 'description']
    inlines = [ExpenseShareInline]
    date_hierarchy = 'date'


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ['from_user', 'to_user', 'amount', 'group', 'date']
    list_filter = ['group', 'date']