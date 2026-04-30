import bleach
from bs4 import BeautifulSoup, Comment
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "em",
    "h2",
    "h3",
    "h4",
    "li",
    "ol",
    "p",
    "strong",
    "ul",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

STRIP_ENTIRELY = [
    "button",
    "embed",
    "form",
    "iframe",
    "input",
    "meta",
    "object",
    "script",
    "select",
    "style",
    "svg",
    "textarea",
]


def sanitize_rich_text(value):
    if not value:
        return ""

    soup = BeautifulSoup(value, "html.parser")

    for tag in soup.find_all(STRIP_ENTIRELY):
        tag.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    cleaned = bleach.clean(
        str(soup),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return cleaned


@register.filter(name="sanitize_html")
def sanitize_html(value):
    return mark_safe(sanitize_rich_text(value))
