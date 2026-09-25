from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "currency", "stock_quantity", "is_active", "created_at"]
    list_filter = ["is_active", "currency"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
