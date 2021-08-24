from django import forms
from django.utils.safestring import mark_safe

from .models import Project
from .utils.FoR_codes import FOR_CODE_CHOICES


class SpanForm(forms.Form):
    def as_span(self):
        """
        Return this form rendered as HTML <span>s.
        """
        return self._html_output(
            normal_row='<span%(html_class_attr)s>%(label)s %(field)s%(help_text)s</span>',
            error_row='%s',
            row_ender='</span>',
            help_text_html='<span class="helptext">%s</span>',
            errors_on_separate_row=True,
        )


class DivModelForm(forms.ModelForm):
    def as_div(self):
        """
        Return this form rendered as HTML <div>s.
        """
        return self._html_output(
            normal_row='<div%(html_class_attr)s>%(label)s %(help_text)s%(field)s</div>',
            error_row='%s',
            row_ender='</div>',
            help_text_html='<div class="small">%s</div>',
            errors_on_separate_row=True,
        )


class UserSearchForm(SpanForm):
    uid = forms.CharField(required=False, label="Username")
    mail = forms.CharField(required=False, label="Email Address")
    givenName = forms.CharField(required=False, label="Given Name")
    surname = forms.CharField(required=False, label="Surname")
    commonName = forms.CharField(required=False, label="Common Name")

    def is_valid(self):
        if super(UserSearchForm, self).is_valid():
            for search_input in self.cleaned_data.values():
                if search_input:
                    return True
            self.add_error(None, "You must fill at least one field")
            return False
        return False


class CustomRadioSelect(forms.RadioSelect):
    template_name = "researcher_workspace/forms/widgets/custom_radio_select.html" # A copy of django/forms/widgets/multiple_input.html
    option_template_name = "researcher_workspace/forms/widgets/custom_radio_select_options.html" # A copy of django/forms/widgets/input_option.html


class ProjectForm(DivModelForm):
    class Meta:
        model = Project
        fields = ['title', 'description', 'FoR_code', 'FoR_code2', 'ARO', 'sensitive_data', 'additional_comments']
    title = forms.CharField(max_length=100)
    description = forms.CharField(widget=forms.Textarea)
    FoR_code = forms.ChoiceField(choices=FOR_CODE_CHOICES, label="Field of Research Code",
        help_text='Select up to two Field of Research (FOR) codes describing your work (minimum one).'
                  ' For more information on FOR codes please refer to the '
                  '<a href="https://www.abs.gov.au/AUSSTATS/abs@.nsf/Lookup/1297.0Main+Features12020?OpenDocument"'
                  ' target="_blank">Australian Bureau of Statistics website</a>.',
    )
    FoR_code.widget.option_template_name = "researcher_workspace/forms/widgets/FoR_code_select_option.html"
    FoR_code.widget.attrs['class'] = 'alt'
    FoR_code2 = forms.ChoiceField(choices=FOR_CODE_CHOICES, required=False,
                                  label="Optional second Field of Research Code"
    )
    FoR_code2.widget.option_template_name = "researcher_workspace/forms/widgets/FoR_code_select_option.html"
    FoR_code2.widget.attrs['class'] = 'alt'
    ARO = forms.EmailField(label="Accountable Resource Owner (ARO)", help_text=
        '<div class="small">Please enter the email address of the project\'s ARO</div>'
        '<ul style="padding-bottom:0;">'
            '<li>For UoM academics on academic research projects specify the most senior University of Melbourne '
        'investigator.</li>'
            '<li>For PhD/Masters by Research on higher degree research projects specify the most senior University of '
        'Melbourne supervisor.</li>'
            '<li>For professional staff on other activities specify the academic sponsor, head of the managing '
        'organisation unit, or line supervisor.</li>'
        '</ul>',
    )
    BOOLEAN_CHOICES = ((True, mark_safe('<span>Yes</span>')), (False, mark_safe('<span>No</span>')))
    # Filtering fields
    sensitive_data = forms.ChoiceField(
        label="Does your project involve sensitive data?",
        label_suffix='',
        # uses items in BOOLEAN_CHOICES
        choices=BOOLEAN_CHOICES,
        widget=CustomRadioSelect,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['additional_comments'].help_text = "For any project related requests"


class PermissionRequestForm(forms.Form):
    feature_options = forms.MultipleChoiceField(label='Options', choices=(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, choices=None, **kwargs):
        super(PermissionRequestForm, self).__init__(*args, **kwargs)
        if choices:
            self.fields['feature_options'].choices = choices
