from urllib.parse import urlsplit

from django import template

register = template.Library()


@register.filter
def journal_social_url(image, request):
    if not image or not request:
        return ""

    try:

        # Prefer a LinkedIn-compatible card for this journal.
        journal = getattr(request, "journal", None)
        favicon = getattr(journal, "favicon", None)

        for candidate in (favicon, image):
            if not candidate or not getattr(candidate, "name", None):
                continue

            filename = (
                candidate.name.rsplit(".", 1)[0]
                + "_social_linkedin_1200x627_v1.png"
            )

            if candidate.storage.exists(filename):
                image_url = candidate.storage.url(filename)

                if image_url.startswith(("https://", "http://")):
                    return image_url

                return request.build_absolute_uri(image_url)

        name = image.name

        if name.lower().endswith(".svg"):
            base = name.rsplit(".", 1)[0]
            small = base + "_social_160x90.png"
            name = small if image.storage.exists(small) else base + "_social.png"

            if not image.storage.exists(name):
                return ""

            url = image.storage.url(name)
        else:
            url = image.url

        parsed = urlsplit(url)

        if parsed.scheme in ("http", "https"):
            return url

        if parsed.scheme or parsed.netloc:
            return ""

        return request.build_absolute_uri(url)

    except (AttributeError, ValueError, OSError):
        return ""
