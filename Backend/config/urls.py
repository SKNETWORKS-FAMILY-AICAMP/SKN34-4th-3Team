from django.urls import path

from config.api import api

urlpatterns = [path("", api.urls)]
