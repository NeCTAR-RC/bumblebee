{% block script %}
var beenClicked = false;
{% if "DELETE_BUTTON" in buttons_to_display %}
function delete_{{ app_name }}_{{ operating_system.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":delete_vm" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}
{% endif %}

{% if "REBOOT_BUTTON" in buttons_to_display %}
function reboot_{{ app_name }}_{{ operating_system.capitalize }}_hard(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":reboot_vm" as url_path %}
        window.location.href = "{% url url_path vm_id 'HARD' %}";
        {% endwith %}
    }
}

function reboot_{{ app_name }}_{{ operating_system.capitalize }}_soft(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":reboot_vm" as url_path %}
        window.location.href = "{% url url_path vm_id 'SOFT' %}";
        {% endwith %}
    }
}
{% endif %}

{% if "SHELVE_BUTTON" in buttons_to_display %}
function shelve_{{ app_name }}_{{ operating_system.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":shelve_vm" as url_path %}
        window.location.href = "{% url url_path vm_id %}";
        {% endwith %}
    }
}
{% endif %}

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
