from datetime import timedelta
from unittest.mock import patch

from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings

from researcher_workspace.templatetags.active_link import active_link
from researcher_workspace.templatetags.class_tag import (
    get_attr, get_class, get_dir,
)
from researcher_workspace.templatetags.data_as_table import (
    iterable, print_2d_list_in_table_body, print_data_as_html_table,
)
from researcher_workspace.templatetags.datetime import period, time_of_day
from researcher_workspace.templatetags.group_filters import has_group
from researcher_workspace.templatetags.settings import (
    add_setting, get_setting,
)
from researcher_workspace.tests.factories import UserFactory


class DatetimeTagTests(TestCase):
    def test_period_minutes_only(self):
        self.assertEqual("5 minutes", period(timedelta(minutes=5)))

    def test_period_hours_only(self):
        self.assertEqual("2 hours", period(timedelta(hours=2)))

    def test_period_hours_and_minutes(self):
        self.assertEqual(
            "2 hours and 5 minutes",
            period(timedelta(hours=2, minutes=5)))

    def test_period_days_only(self):
        self.assertEqual("3 days", period(timedelta(days=3)))

    def test_period_days_and_hours(self):
        self.assertEqual(
            "3 days and 2 hours",
            period(timedelta(days=3, hours=2)))

    def test_period_days_and_minutes(self):
        self.assertEqual(
            "3 days and 5 minutes",
            period(timedelta(days=3, minutes=5)))

    def test_period_days_hours_and_minutes(self):
        self.assertEqual(
            "3 days, 2 hours and 5 minutes",
            period(timedelta(days=3, hours=2, minutes=5)))

    def test_period_zero(self):
        self.assertEqual("0 minutes", period(timedelta()))

    @patch('researcher_workspace.templatetags.datetime.datetime')
    def test_time_of_day_morning(self, mock_dt):
        mock_dt.now.return_value.hour = 8
        self.assertEqual("Morning", time_of_day())

    @patch('researcher_workspace.templatetags.datetime.datetime')
    def test_time_of_day_afternoon(self, mock_dt):
        mock_dt.now.return_value.hour = 14
        self.assertEqual("Afternoon", time_of_day())

    @patch('researcher_workspace.templatetags.datetime.datetime')
    def test_time_of_day_evening(self, mock_dt):
        mock_dt.now.return_value.hour = 20
        self.assertEqual("Evening", time_of_day())


class DataAsTableTagTests(TestCase):
    def test_iterable_list(self):
        self.assertTrue(iterable([1, 2]))

    def test_iterable_dict(self):
        self.assertTrue(iterable({'a': 1}))

    def test_iterable_string(self):
        self.assertFalse(iterable("hello"))

    def test_iterable_int(self):
        self.assertFalse(iterable(7))

    def test_print_data_as_html_table_dict(self):
        out = print_data_as_html_table({'a': 1, 'b': 2})
        self.assertIn("<tr><td>a</td><td>1</td></tr>", out)
        self.assertIn("<tr><td>b</td><td>2</td></tr>", out)
        self.assertTrue(out.startswith("<table>"))
        self.assertTrue(out.endswith("</table>"))

    def test_print_data_as_html_table_list(self):
        out = print_data_as_html_table([1, 2])
        self.assertIn("<tr><td>1</td></tr>", out)
        self.assertIn("<tr><td>2</td></tr>", out)

    def test_print_data_as_html_table_nested_dict(self):
        out = print_data_as_html_table({'a': {'b': 'c'}})
        self.assertIn("<tr><td>b</td><td>c</td></tr>", out)

    def test_print_data_as_html_table_nested_list(self):
        out = print_data_as_html_table([[1, 2], [3]])
        self.assertIn("<tr><td>1</td></tr>", out)

    def test_print_2d_list_in_table_body(self):
        out = print_2d_list_in_table_body([[1, 2], [3, 4]])
        self.assertTrue(out.startswith("<tbody>"))
        self.assertTrue(out.endswith("</tbody>"))
        self.assertIn("<td>1</td>", out)
        self.assertIn("<td>4</td>", out)

    def test_print_2d_list_in_table_body_with_iterable(self):
        out = print_2d_list_in_table_body([[[1, 2], 3]])
        self.assertIn("<td>1</td>", out)


class ClassTagTests(TestCase):
    def test_get_class(self):
        self.assertEqual("int", get_class(1))
        self.assertEqual("str", get_class("a"))

    def test_get_dir(self):
        self.assertIn("upper", get_dir("hi"))

    def test_get_attr(self):
        class Obj:
            x = 5
        self.assertEqual(5, get_attr(Obj(), "x"))


class SettingsTagTests(TestCase):
    @override_settings(SOME_TEMPLATE_SETTING="value-x")
    def test_get_setting_present(self):
        self.assertEqual("value-x", get_setting("SOME_TEMPLATE_SETTING"))

    def test_get_setting_missing(self):
        self.assertEqual("", get_setting("NOT_A_SETTING_AT_ALL"))

    @override_settings(SOMETHING_ELSE="abc")
    def test_add_setting(self):
        ctx = Context({})
        result = add_setting(ctx, "SOMETHING_ELSE", "the_value")
        self.assertEqual("", result)
        self.assertEqual("abc", ctx["the_value"])


class ActiveLinkTagTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_active_link_no_request(self):
        result = active_link(Context({}), "home")
        self.assertEqual("", result)

    def test_active_link_match(self):
        request = self.factory.get("/home/")
        result = active_link(Context({"request": request}), "home")
        self.assertEqual("active", result)

    def test_active_link_no_match(self):
        request = self.factory.get("/about/")
        result = active_link(
            Context({"request": request}), "home", inactive_class="off")
        self.assertEqual("off", result)

    def test_active_link_strict(self):
        request = self.factory.get("/home/extra")
        # non-strict: starts-with match returns active
        result = active_link(Context({"request": request}), "home")
        self.assertEqual("active", result)
        # strict: doesn't match
        result = active_link(
            Context({"request": request}), "home", strict=True,
            inactive_class="off")
        self.assertEqual("off", result)

    def test_active_link_no_reverse_match(self):
        request = self.factory.get("/home/")
        result = active_link(
            Context({"request": request}), "no_such_view",
            inactive_class="off")
        self.assertEqual("off", result)

    def test_active_link_multi_views(self):
        request = self.factory.get("/home/")
        result = active_link(
            Context({"request": request}), "no_such_view||home")
        self.assertEqual("active", result)

    def test_active_link_custom_class(self):
        request = self.factory.get("/home/")
        result = active_link(
            Context({"request": request}), "home", css_class="hot")
        self.assertEqual("hot", result)


class GroupFilterTests(TestCase):
    def test_has_group_false(self):
        user = UserFactory.create()
        self.assertFalse(has_group(user, "Some Group"))

    def test_has_group_true(self):
        from django.contrib.auth.models import Group
        user = UserFactory.create()
        group = Group.objects.create(name="Some Group")
        user.groups.add(group)
        self.assertTrue(has_group(user, "Some Group"))


class TemplateRenderingTests(TestCase):
    def test_data_as_table_filter_in_template(self):
        tpl = Template(
            "{% load data_as_table %}{{ data|print_data_as_html_table }}")
        out = tpl.render(Context({"data": {"k": "v"}}))
        self.assertIn("<td>k</td>", out)

    def test_get_class_filter_in_template(self):
        tpl = Template("{% load class_tag %}{{ value|get_class }}")
        out = tpl.render(Context({"value": "hi"}))
        self.assertEqual("str", out)
