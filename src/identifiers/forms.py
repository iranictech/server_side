import re

from django import forms

from identifiers import models


class IdentifierForm(forms.ModelForm):
    class Meta:
        model = models.Identifier
        fields = (
            "id_type",
            "identifier",
            "enabled",
        )

    def __init__(self, *args, **kwargs):
        self.article = kwargs.pop("article")
        super(IdentifierForm, self).__init__(*args, **kwargs)

        from identifiers.zenodo_models import ZenodoDeposit

        has_doi = models.Identifier.objects.filter(
            article=self.article,
            id_type="doi",
        ).exists()

        has_deposit = ZenodoDeposit.objects.filter(
            article=self.article,
            is_sandbox=False,
        ).exists()

        if not self.instance.pk or self.instance.id_type != "doi":
            if has_doi or has_deposit:
                self.fields["id_type"].choices = [
                    (value, label)
                    for value, label in self.fields["id_type"].choices
                    if value != "doi"
                ]

    def clean(self):
        super().clean()
        cleaned_data = self.cleaned_data

        # Test identifier against Regex
        id_type = self.cleaned_data.get("id_type")
        identifier = self.cleaned_data.get("identifier")

        if id_type == "doi":
            pattern = models.DOI_RE
        else:
            pattern = models.PUB_ID_RE

        if not id_type or not identifier:
            return cleaned_data

        if not pattern.match(identifier):
            self.add_error(
                "identifier",
                "Invalid identifier format.",
            )

        # Check identifier doesn't exist elsewhere
        idents = models.Identifier.objects.filter(
            id_type=id_type,
            identifier=identifier,
        )

        if self.instance:
            idents = idents.exclude(id=self.instance.id)

        if id_type == "doi" and idents.exists():
            self.add_error(
                "identifier",
                "This DOI already exists for another Article.",
            )
        else:
            if idents.filter(
                article__journal=self.article.journal,
            ).exists():
                self.add_error(
                    "identifier",
                    "This identifier already exists on: {}.".format(
                        " ".join([ident.article.title for ident in idents])
                    ),
                )

        return cleaned_data

    def save(self, commit=True):
        identifier = super(IdentifierForm, self).save(commit=False)

        if self.article:
            identifier.article = self.article

        if commit:
            pass
            identifier.save()

        return identifier
