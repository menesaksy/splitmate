from django.contrib import admin
from django.utils.html import format_html
from .models import Group, Membership, Expense, ExpenseShare, Settlement, Notification, Category, RecurringExpense


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('colored_name', 'icon')
    search_fields = ('name',)

    def colored_name(self, obj):
        return format_html(
            '<span style="background:{}; color:#fff; padding:2px 10px; border-radius:4px;">{}</span>',
            obj.color, obj.name
        )
    colored_name.short_description = 'Kategori'


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ('user', 'role', 'joined_at')
    readonly_fields = ('joined_at',)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency', 'member_count', 'expense_count', 'total', 'is_active', 'created_at')
    list_filter = ('currency', 'is_active')
    search_fields = ('name',)
    readonly_fields = ('invite_code', 'created_at')
    inlines = [MembershipInline]

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Üye'

    def expense_count(self, obj):
        return obj.expenses.count()
    expense_count.short_description = 'Harcama'

    def total(self, obj):
        return f"{obj.total_expenses()} {obj.currency}"
    total.short_description = 'Toplam'


class ExpenseShareInline(admin.TabularInline):
    model = ExpenseShare
    extra = 0
    fields = ('user', 'amount')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'group', 'amount_display', 'paid_by', 'split_type', 'category', 'date')
    list_filter = ('split_type', 'category', 'group')
    search_fields = ('title', 'description', 'paid_by__username')
    readonly_fields = ('created_at',)
    inlines = [ExpenseShareInline]
    date_hierarchy = 'date'

    def amount_display(self, obj):
        return f"{obj.amount} {obj.group.currency}"
    amount_display.short_description = 'Tutar'


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ('group', 'from_user', 'to_user', 'amount', 'date', 'note')
    list_filter = ('group',)
    search_fields = ('from_user__username', 'to_user__username')
    date_hierarchy = 'date'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('user__username', 'title')
    readonly_fields = ('created_at',)
    actions = ['mark_read']

    def mark_read(self, request, queryset):
        queryset.update(is_read=True)
        self.message_user(request, f'{queryset.count()} bildirim okundu olarak işaretlendi.')
    mark_read.short_description = 'Okundu olarak işaretle'


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'group', 'role', 'joined_at')
    list_filter = ('role', 'group')
    search_fields = ('user__username', 'group__name')
    readonly_fields = ('joined_at',)


@admin.register(RecurringExpense)
class RecurringExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'group', 'amount', 'frequency', 'next_run', 'is_active')
    list_filter = ('frequency', 'is_active', 'group')
    search_fields = ('title', 'group__name')
    readonly_fields = ('created_at',)