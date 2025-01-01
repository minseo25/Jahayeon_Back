from django.urls import path

from . import views

urlpatterns = [
    path("gpt/generate/", views.gpt_generate, name="gpt_generate"),
    path("gemini/generate/", views.gemini_generate, name="gemini_generate"),
]
