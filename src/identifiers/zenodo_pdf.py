"""
Select and safely open a public local Janeway PDF galley.

No database writes and no Zenodo API requests.
"""

from contextlib import contextmanager
from pathlib import Path

from django.conf import settings


class ZenodoPDFError(RuntimeError):
    """PDF cannot be safely prepared for a Zenodo upload."""


@contextmanager
def open_public_article_pdf(article):
    """
    Yield (binary_file, safe_filename) for one public local PDF.

    Raises ZenodoPDFError if the PDF is ambiguous, missing,
    inaccessible, or invalid.
    """

    if article.pk is None:
        raise ZenodoPDFError("Article must be saved")

    galleys = list(
        article.pdfs.filter(
            public=True,
            is_remote=False,
        )
        .select_related("file")
        .order_by("sequence", "pk")[:2]
    )

    if not galleys:
        raise ZenodoPDFError("No public local PDF galley")

    if len(galleys) > 1:
        raise ZenodoPDFError(
            "Multiple public PDF galleys; explicit selection required"
        )

    galley = galleys[0]
    file = galley.file

    if file is None:
        raise ZenodoPDFError("Galley has no file")

    if file.is_remote:
        raise ZenodoPDFError("Remote files are not supported")

    if file.article_id != article.pk:
        raise ZenodoPDFError("PDF file belongs to another article")

    if file.mime_type.lower().strip() != "application/pdf":
        raise ZenodoPDFError("Galley file is not a PDF")

    root = (
        Path(settings.BASE_DIR)
        / "files"
        / "articles"
        / str(article.pk)
    ).resolve()

    try:
        path = Path(file.get_file_path(article)).resolve(strict=True)

        if path.parent != root:
            raise ZenodoPDFError(
                "PDF path is outside the expected article directory"
            )

        if not path.is_file():
            raise ZenodoPDFError("PDF path is not a regular file")

        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ZenodoPDFError("Invalid PDF file signature")

            stream.seek(0)

            filename = f"article-{article.pk}.pdf"

            yield stream, filename

    except (OSError, ValueError) as exc:
        raise ZenodoPDFError(
            "PDF file cannot be accessed"
        ) from exc
