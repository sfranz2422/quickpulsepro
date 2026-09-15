"""Turning teacher-authored markdown into HTML that is safe to show students.

Questions are written by teachers, and several teachers share this site, so
the rendered HTML is sanitized rather than trusted. Code fences survive;
scripts and event handlers do not.
"""

import markdown as markdown_lib
import nh3


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
