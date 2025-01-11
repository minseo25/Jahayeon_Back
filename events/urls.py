from django.urls import path

from . import views

urlpatterns = [
    path("create/", views.events_create, name="events_create"),
    path("<int:event_id>/", views.events_detail, name="events_detail"),
    path("<int:event_id>/join/", views.events_join, name="events_join"),
    path("<int:event_id>/complete/", views.events_complete, name="events_complete"),
    path("", views.events_list, name="events"),
    path("my/", views.events_my, name="events_my"),
]
