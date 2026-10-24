from .models import AbstractIndexing


def yield_homepage_element_context(request, homepage_elements):
    if (
        homepage_elements is not None
        and homepage_elements.filter(name="Abstract Indexing").exists()
    ):
        indexings = AbstractIndexing.objects.filter(
            journal=request.journal,
            is_active=True,
        ).order_by(
            "ordering",
            "name",
        )

        return {
            "indexings": indexings,
        }

    return {}