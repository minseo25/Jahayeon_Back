from django.urls import path

from . import views

urlpatterns = [
    path("", views.parties_list, name="parties"),
    path("create/", views.parties_create, name="parties_create"),
    path("<int:party_id>/", views.parties_detail, name="parties_detail"),
    path("<int:party_id>/join/", views.parties_join, name="parties_join"),
    path("<int:party_id>/start/", views.parties_start, name="parties_start"),
    path("<int:party_id>/end/", views.parties_end, name="parties_end"),
]
