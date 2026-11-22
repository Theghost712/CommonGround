from django.contrib import admin

from .models import Call


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "caller", "callee", "status", "answered_at", "ended_at"]
    list_filter = ["kind", "status"]
    search_fields = ["caller__username", "callee__username"]
    readonly_fields = [field.name for field in Call._meta.fields]
