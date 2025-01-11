from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.user_profile, name="user_profile"),
    path("history/", views.user_history, name="user_history"),
]
