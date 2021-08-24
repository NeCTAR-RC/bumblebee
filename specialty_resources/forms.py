from django import forms

from researcher_workspace.models import get_permission_feature_options_for_latest_project
from specialty_resources.constants import OS_CHOICES
from specialty_resources.utils.utils import get_vm_info


class SpecialtyResourcesCreationForm(forms.Form):
    operating_system = forms.ChoiceField(choices=OS_CHOICES, label="Please select the Operating System")
    flavor = forms.ChoiceField(choices=(), label="Please select the Flavor")

    def __init__(self, *args, current_user, **kwargs):
        super(SpecialtyResourcesCreationForm, self).__init__(*args, **kwargs)
        specialty_resources_vm_info = get_vm_info()
        self.fields['flavor'].choices = get_permission_feature_options_for_latest_project(current_user, specialty_resources_vm_info.FEATURE)
