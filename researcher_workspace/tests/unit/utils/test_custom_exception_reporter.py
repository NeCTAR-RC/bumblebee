import sys
from unittest import TestCase

from django.test import RequestFactory

from researcher_workspace.utils.custom_exception_reporter import (
    CustomExceptionReporter,
)


class CustomExceptionReporterTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        try:
            raise ValueError("oops")
        except ValueError:
            self.exc_info = sys.exc_info()

    def test_get_traceback_text(self):
        request = self.factory.get("/some/path")
        reporter = CustomExceptionReporter(request, *self.exc_info)
        out = reporter.get_traceback_text()
        self.assertIn("ValueError", out)
        self.assertIn("oops", out)

    def test_get_traceback_html(self):
        request = self.factory.get("/some/path")
        reporter = CustomExceptionReporter(request, *self.exc_info)
        out = reporter.get_traceback_html()
        self.assertIn("ValueError", out)
        self.assertIn("oops", out)
