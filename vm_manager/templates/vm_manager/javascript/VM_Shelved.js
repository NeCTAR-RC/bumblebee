var beenClicked = false;
function unshelve_{{ app_name }}_{{ desktop_type.id }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":unshelve_vm" as url_path %}
        window.location.href = "{% url url_path desktop_type.id %}";
        {% endwith %}
    }
}
function delete_{{ app_name }}_{{ desktop_type.id }}(tag) {
    if (!beenClicked) {
        beenClicked = true;
        tag.disabled = true;
        {% with app_name|add:":delete_shelved_vm" as url_path %}
        window.location.href = "{% url url_path desktop_type.id %}";
        {% endwith %}
    }
}
