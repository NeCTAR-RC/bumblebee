var beenClicked = false;
function reboot_{{ app_name }}_{{ desktop_type.id }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":reboot_vm" as url_path %}
        window.location.href = "{% url url_path vm_id 'HARD' %}";
        {% endwith %}
    }
}
