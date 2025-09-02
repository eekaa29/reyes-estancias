from django.contrib import admin
from django.utils.html import format_html
from .models import Property, PropertyImage
# Register your models here.


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1
    fields = ("preview", "image", "position", "cover")
    readonly_fields = ("preview",)

    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:60px;border-radius:6px;">', obj.image.url)
        return "—"

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("name", "max_people", "nightly_price")
    inlines = [PropertyImageInline]