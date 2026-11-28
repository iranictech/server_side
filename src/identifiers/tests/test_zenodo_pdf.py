import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from identifiers.zenodo_pdf import (
    ZenodoPDFError,
    open_public_article_pdf,
)


class ZenodoPDFTests(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.base = Path(temporary.name)
        self.article_id = 40

        self.folder = (
            self.base / "files" / "articles" / str(self.article_id)
        )
        self.folder.mkdir(parents=True)

        self.path = self.folder / "test.pdf"
        self.path.write_bytes(b"%PDF-1.4\nTest PDF data\n%%EOF")

        self.file = SimpleNamespace(
            article_id=self.article_id,
            mime_type="application/pdf",
            is_remote=False,
            get_file_path=lambda article: str(self.path),
        )

        self.galley = SimpleNamespace(file=self.file)

        self.pdfs = MagicMock()
        queryset = self.pdfs.filter.return_value
        queryset = queryset.select_related.return_value
        queryset = queryset.order_by.return_value
        queryset.__getitem__.return_value = [self.galley]

        self.article = SimpleNamespace(
            pk=self.article_id,
            pdfs=self.pdfs,
        )

        settings_patch = patch(
            "identifiers.zenodo_pdf.settings",
            SimpleNamespace(BASE_DIR=str(self.base)),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

    def test_valid_pdf(self):
        with open_public_article_pdf(self.article) as result:
            stream, filename = result

            self.assertEqual(filename, "article-40.pdf")
            self.assertEqual(stream.read(5), b"%PDF-")

        self.pdfs.filter.assert_called_once_with(
            public=True,
            is_remote=False,
        )

    def test_no_public_pdf(self):
        self.pdfs.filter.return_value \
            .select_related.return_value \
            .order_by.return_value \
            .__getitem__.return_value = []

        with self.assertRaises(ZenodoPDFError):
            with open_public_article_pdf(self.article):
                pass

    def test_multiple_public_pdfs(self):
        self.pdfs.filter.return_value \
            .select_related.return_value \
            .order_by.return_value \
            .__getitem__.return_value = [
                self.galley,
                self.galley,
            ]

        with self.assertRaisesRegex(
            ZenodoPDFError, "Multiple public"
        ):
            with open_public_article_pdf(self.article):
                pass

    def test_wrong_mime_type(self):
        self.file.mime_type = "text/plain"

        with self.assertRaises(ZenodoPDFError):
            with open_public_article_pdf(self.article):
                pass

    def test_remote_file(self):
        self.file.is_remote = True

        with self.assertRaises(ZenodoPDFError):
            with open_public_article_pdf(self.article):
                pass

    def test_other_article_file(self):
        self.file.article_id = 99

        with self.assertRaises(ZenodoPDFError):
            with open_public_article_pdf(self.article):
                pass

    def test_missing_file(self):
        self.path.unlink()

        with self.assertRaises(ZenodoPDFError):
            with open_public_article_pdf(self.article):
                pass

    def test_invalid_pdf_signature(self):
        self.path.write_bytes(b"NOT A PDF")

        with self.assertRaisesRegex(
            ZenodoPDFError, "Invalid PDF"
        ):
            with open_public_article_pdf(self.article):
                pass


    def test_path_outside_article_directory(self):
        outside = self.base / "outside.pdf"
        outside.write_bytes(b"%PDF-1.4\\nExternal file")

        self.file.get_file_path = lambda article: str(outside)

        with self.assertRaisesRegex(
            ZenodoPDFError, "outside the expected"
        ):
            with open_public_article_pdf(self.article):
                pass

    def test_symlink_to_external_pdf(self):
        outside = self.base / "external.pdf"
        outside.write_bytes(b"%PDF-1.4\\nExternal file")

        link = self.folder / "linked.pdf"
        link.symlink_to(outside)

        self.file.get_file_path = lambda article: str(link)

        with self.assertRaisesRegex(
            ZenodoPDFError, "outside the expected"
        ):
            with open_public_article_pdf(self.article):
                pass

    def test_missing_article_id(self):
        self.article.pk = None

        with self.assertRaisesRegex(
            ZenodoPDFError, "must be saved"
        ):
            with open_public_article_pdf(self.article):
                pass


if __name__ == "__main__":
    unittest.main()
