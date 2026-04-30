from django.contrib import admin

# Register your models here.

from .models import Profile


@admin.action(description='Approve selected host applications')
def approve_host_requests(modeladmin, request, queryset):
    queryset.update(is_host=True, host_requested=False)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_host', 'host_requested')
    list_filter = ('is_host', 'host_requested')
    search_fields = ('user__username', 'user__email')
    actions = [approve_host_requests]
