from django import template
from django.utils.safestring import mark_safe

from ..markdown_utils import render_markdown

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text):
    """Renders markdown. Safe because render_markdown sanitizes its output."""
    return mark_safe(render_markdown(text))
