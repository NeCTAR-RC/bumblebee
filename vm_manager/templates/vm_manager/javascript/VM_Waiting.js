var {{ app_name }}_{{ desktop_type.id }}_timer = {{ what_to_show }};
reloaded = false;
var x = setInterval(function () {
    {{ app_name }}_{{ desktop_type.id }}_timer = {{ app_name }}_{{ desktop_type.id }}_timer - 1;
    if ({{ app_name }}_{{ desktop_type.id }}_timer <= 0 && !reloaded) {
        reloaded = true;
        window.location.reload(1);
    }
    const {{ app_name }}_{{ desktop_type.id }}_minutes = (Math.max(Math.floor({{ app_name }}_{{ desktop_type.id }}_timer/60), 0)).toString()
    const {{ app_name }}_{{ desktop_type.id }}_seconds = (Math.max({{ app_name }}_{{ desktop_type.id }}_timer%60, 0)).toString().padStart(2, "0")
    document.getElementById("{{ app_name }}-{{ desktop_type.id }}-time").innerHTML = {{ app_name }}_{{ desktop_type.id }}_minutes + ":" + {{ app_name }}_{{ desktop_type.id }}_seconds;
}, 1000);

async function poll_status(url, interval) {
    while(true) {
        await new Promise(r => setTimeout(r, interval));
        fetch(url)
            .then(resp => resp.json())
            .then(vm_status => {
                console.log(vm_status);
                if (vm_status.status != "{{ VM_WAITING }}") {
                    reloaded = true;
                    window.location.reload(1);
                } else {
                    var bar = document.getElementById(
                        "{{ app_name }}-{{ desktop_type.id }}-bar");
                    var progress = vm_status.status_progress;
                    bar.setAttribute("aria-valuenow", progress);
                    bar.setAttribute("style", "width: " + progress + "%");
                    bar.innerHTML = vm_status.status_message;
                }
            });
    }
}

{% with app_name|add:":status_vm" as url_path %}
var status_url = "{% url url_path desktop_type.id %}";
{% endwith %}
poll_status(status_url, 5000)
