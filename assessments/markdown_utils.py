"""Turning teacher-authored markdown into HTML that is safe to show students.

Questions are written by teachers, and several teachers share this site, so
the rendered HTML is sanitized rather than trusted. Code fences survive;
scripts and event handlers do not.
"""

import markdown as markdown_lib
import nh3

from .models import BLANK_MARKER


MARKDOWN_EXTENSIONS = [
    "fenced_code",   # ```python ... ```
    "tables",
    "sane_lists",
    "nl2br",         # a single newline is a line break, which is what
                     # people expect when typing into a textarea
]

# Everything nh3 allows by default, minus nothing, plus the bits fenced code
# and tables need. Deliberately no <script>, <style>, <iframe> or <form>.
ALLOWED_TAGS = {
    "p", "br", "hr",
    "strong", "b", "em", "i", "u", "s", "del", "ins", "mark", "sub", "sup",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "blockquote",
    "pre", "code", "kbd", "samp", "var",
    "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
    "span", "div",
}

ALLOWED_ATTRIBUTES = {
    # No "rel" here: nh3 manages it itself via link_rel below.
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
    # Python-Markdown puts the fence language here, which highlight.js reads.
    "code": {"class"},
    "pre": {"class"},
    "span": {"class"},
    "div": {"class"},
    "th": {"align"},
    "td": {"align"},
}


def render_markdown(text):
    """Markdown in, sanitized HTML out."""
    if not text:
        return ""

    html = markdown_lib.markdown(
        text,
        extensions=MARKDOWN_EXTENSIONS,
        output_format="html",
    )

    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel="noopener noreferrer",
    )


# Stands in for a blank while the markdown renders. Letters and digits only,
# so markdown leaves it alone and nh3 has nothing to strip.
BLANK_TOKEN = "QPBLANK{}QP"


def render_markdown_with_blanks(text, blank_html):
    """Renders a fill in the blank prompt, putting blank_html(n) at each ___.

    The blanks go in after sanitizing, so the inputs they become are ours and
    never pass through the teacher's markdown. Returns (html, blanks placed).
    """
    count = 0

    def to_token(match):
        nonlocal count
        count += 1
        return BLANK_TOKEN.format(count)

    html = render_markdown(BLANK_MARKER.sub(to_token, text or ""))

    for number in range(1, count + 1):
        html = html.replace(BLANK_TOKEN.format(number), blank_html(number), 1)

    return html, count
