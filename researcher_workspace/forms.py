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
    # A copy of django/forms/widgets/multiple_input.html
    template_name = "researcher_workspace/forms/widgets/custom_radio_select.html"
    # A copy of django/forms/widgets/input_option.html
    option_template_name = "researcher_workspace/forms/widgets/custom_radio_select_options.html"


class ProjectForm(forms.ModelForm):

    class Meta:
        model = Project
        fields = ['title', 'description', 'FoR_code', 'FoR_code2',
                  'chief_investigator']

    title = forms.CharField(max_length=100)
    title.widget.attrs['class'] = 'form-control'
    description = forms.CharField(widget=forms.Textarea)
    description.widget.attrs['class'] = 'form-control'
    chief_investigator = forms.EmailField(max_length=100)
    chief_investigator.widget.attrs['class'] = 'form-control'
    FoR_code = forms.ChoiceField(choices=FOR_CODE_CHOICES)
    FoR_code.widget.template_name = \
        "researcher_workspace/forms/widgets/FoR_code_select.html"
    FoR_code.widget.option_template_name = \
        "researcher_workspace/forms/widgets/FoR_code_select_option.html"
    FoR_code.widget.attrs['class'] = 'alt form-control'
    FoR_code2 = forms.ChoiceField(choices=FOR_CODE_CHOICES, required=False)
    FoR_code2.widget.template_name = \
        "researcher_workspace/forms/widgets/FoR_code_select.html"
    FoR_code2.widget.option_template_name = \
        "researcher_workspace/forms/widgets/FoR_code_select_option.html"
    FoR_code2.widget.attrs['class'] = 'alt form-control'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class PermissionRequestForm(forms.Form):
    feature_options = forms.MultipleChoiceField(label='Options', choices=(), widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, choices=None, **kwargs):
        super(PermissionRequestForm, self).__init__(*args, **kwargs)
        if choices:
            self.fields['feature_options'].choices = choices
