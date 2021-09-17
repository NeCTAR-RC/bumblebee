{% extends 'vm_manager/javascript/VM_Okay_base.js' %}
{% block script %}
function downsize_{{ app_name }}_{{ desktop_type.id.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":downsize_vm" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}

function extend_{{ app_name }}_{{ desktop_type.id.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":extend" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}
{% endblock script %}
