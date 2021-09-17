var beenClicked = false;
function launch_{{ app_name }}_{{ desktop_type.id }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":launch_vm" as url_path %}
        window.location.href = "{% url url_path desktop_type.id %}";
        {% endwith %}
    }
}
