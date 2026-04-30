from django_summernote.admin import SummernoteModelAdmin
from django.contrib import admin
from .models import *

# Register your models here.

class SomeModelAdmin(SummernoteModelAdmin):  # instead of ModelAdmin
    summernote_fields = '__all__'


class BookingCancellationAuditAdmin(admin.ModelAdmin):
    readonly_fields = (
        'booking',
        'actor',
        'cancelled_at',
        'ip_address',
        'user_agent',
        'previous_status',
        'new_status',
        'before_snapshot',
        'after_snapshot',
    )
    list_display = ('booking', 'actor', 'cancelled_at', 'ip_address', 'previous_status', 'new_status')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



admin.site.register(Property,SomeModelAdmin)
admin.site.register(Place)
admin.site.register(PropertyBook)
admin.site.register(BookingCancellationAudit, BookingCancellationAuditAdmin)
admin.site.register(PropertyImages)
admin.site.register(PropertyReview)
admin.site.register(Category)
