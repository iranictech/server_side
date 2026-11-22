"""Optional Gold Journal Finder; existing Search Bar routes remain unchanged."""
from django.urls import path
from .gold_finder import find_journal_fit

urlpatterns = [
    path("gold-finder/", find_journal_fit, name="gold_journal_finder"),
]
