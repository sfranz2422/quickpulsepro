from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..markdown_utils import render_markdown, render_markdown_with_blanks

register = template.Library()


@register.filter(name="markdown")
def markdown_filter(text):
    """Renders markdown. Safe because render_markdown sanitizes its output."""
    return mark_safe(render_markdown(text))


@register.filter(name="question_prompt")
def question_prompt(question):
    """A question's prompt for the teacher. Fill in the blank prompts show a
    numbered slot at each blank instead of the raw underscores."""
    if not question.is_fill_in_blank:
        return markdown_filter(question.prompt)

    html, _ = render_markdown_with_blanks(
        question.prompt,
        lambda number: format_html('<span class="blank-slot">{}</span>', number),
    )

    return mark_safe(html)


@register.simple_tag
def prompt_with_blanks(question, answer=None):
    """A fill in the blank prompt for a student, with a text box at each
    blank holding whatever they typed before. A prompt with no ___ gets one
    box underneath it."""

    def blank_input(number):
        return format_html(
            '<input type="text" class="form-control blank-input" '
            'name="question_{}_{}" value="{}" aria-label="Blank {}" '
            'autocomplete="off" autocapitalize="off" spellcheck="false">',
            question.id,
            number,
            answer.response_at(number - 1) if answer else "",
            number,
        )

    html, placed = render_markdown_with_blanks(question.prompt, blank_input)

    if not placed:
        html += format_html('<p class="mt-3">{}</p>', blank_input(1))

    return mark_safe(html)
