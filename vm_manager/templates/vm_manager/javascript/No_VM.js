var beenClicked = false;
function launch_{{ app_name }}_{{ operating_system.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":launch_vm" as url_path %}
        window.location.href = "{% url url_path operating_system %}";
        {% endwith %}
    }
}