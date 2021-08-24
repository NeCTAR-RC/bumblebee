{% extends 'vm_manager/javascript/VM_Okay_base.js' %}
{% block script %}
{% if "BOOST_BUTTON" in buttons_to_display %}
function supersize_{{ app_name }}_{{ operating_system.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":supersize_vm" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}
{% endif %}
{% endblock script %}
