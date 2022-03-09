from pathlib import Path

from django import template
from django.views import debug

TECHNICAL_500_TEXT_TEMPLATE = "technical_500.txt"
TECHNICAL_500_HTML_TEMPLATE = "technical_500.html"


class CustomExceptionReporter(debug.ExceptionReporter):
    def get_traceback_text(self):
        template_content = self._get_template(TECHNICAL_500_TEXT_TEMPLATE)
        context = template.Context(
            self.get_traceback_data(), autoescape=False, use_l10n=False)
        return template_content.render(context)

    def get_traceback_html(self):
        template_content = self._get_template(TECHNICAL_500_HTML_TEMPLATE)
        context = template.Context(
            self.get_traceback_data(), autoescape=False, use_l10n=False)
        return template_content.render(context)

    @staticmethod
    def _get_template(template_name):
        current_dir = Path(__file__).parent
        with Path(current_dir, template_name).open(encoding='utf-8') as fh:
            return debug.DEBUG_ENGINE.from_string(fh.read())
