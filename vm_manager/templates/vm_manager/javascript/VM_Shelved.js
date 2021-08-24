var beenClicked = false;
function unshelve_{{ app_name }}_{{ operating_system.capitalize }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":unshelve_vm" as url_path %}
        window.location.href = "{% url url_path operating_system %}";
        {% endwith %}
    }
}
