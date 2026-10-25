from django import forms

from .models import AbstractIndexing


class AbstractIndexingForm(forms.ModelForm):

    class Meta:
        model = AbstractIndexing
        fields = (
            "image",
            "name",
            "url",
            "description",
            "ordering",
            "is_active",
        )