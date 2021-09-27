{% extends 'vm_manager/javascript/VM_Okay.js' %}
{% block script %}

{{ block.super }}

{% if "DOWNSIZE_BUTTON" in buttons_to_display %}
function downsize_{{ app_name }}_{{ desktop_type.id }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":downsize_vm" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}
{% endif %}
{% if "EXTEND_BUTTON" in buttons_to_display %}
function extend_{{ app_name }}_{{ desktop_type.id }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":extend" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}
{% endif %}
{% endblock script %}
