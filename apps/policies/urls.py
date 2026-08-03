from django.urls import path

from .views import PlaceholderView

urlpatterns = [
    path("placeholder/", PlaceholderView.as_view(), name="policies-placeholder"),
]
