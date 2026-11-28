from django.core.management.base import BaseCommand

from identifiers import logic as identifier_logic
from submission import models as submission_models


class Command(BaseCommand):
    """Takes an OAI PMH url and pulls information into Janeway."""

    help = "Registers a DOI with Crossref."

    def add_arguments(self, parser):
        """Adds arguments to Django's management command-line parser.

        :param parser: the parser to which the required arguments will be added
        :return: None
        """
        parser.add_argument("article_id")

    def handle(self, *args, **options):
        """Calls the Crossref registration options

        :param args: None
        :param options: Dictionary containing 'article_id'
        :return: None
        """
        article = submission_models.Article.objects.get(pk=options["article_id"])

        identifier = article.get_identifier("doi", object=True)

        if identifier_logic.crossref_blocked_article_ids(
            [article.pk]
        ):
            self.stdout.write(
                "Article DOI is managed by Zenodo. Skipped."
            )
            return

        if not identifier:
            identifier = (
                identifier_logic.generate_crossref_doi_with_pattern(
                    article
                )
            )

        if identifier and identifier.is_doi:
            status, error = identifier.register()
            self.stdout.write(str(status))
        else:
            self.stdout.write("No eligible Crossref DOI.")
