var {{ app_name }}_{{ operating_system }}_timer = {{ what_to_show }};
reloaded = false;
var x = setInterval(function () {
    {{ app_name }}_{{ operating_system }}_timer = {{ app_name }}_{{ operating_system }}_timer - 1;
    if ({{ app_name }}_{{ operating_system }}_timer <= 0 && !reloaded) {
        reloaded = true;
        window.location.reload(1);
    }
    const {{ app_name }}_{{ operating_system }}_minutes = (Math.max(Math.floor({{ app_name }}_{{ operating_system }}_timer/60), 0)).toString()
    const {{ app_name }}_{{ operating_system }}_seconds = (Math.max({{ app_name }}_{{ operating_system }}_timer%60, 0)).toString().padStart(2, "0")
    document.getElementById("{{ app_name }}-{{ operating_system }}-time").innerHTML = {{ app_name }}_{{ operating_system }}_minutes + ":" + {{ app_name }}_{{ operating_system }}_seconds;
}, 1000);

async function poll_status(url, interval) {
  while(true) {
    await new Promise(r => setTimeout(r, interval));
    fetch(url)
      .then(resp => resp.json())
      .then(vmstatus => {
         console.log(vmstatus);
         if (vmstatus.state != "{{ VM_WAITING }}") {
            reloaded = true;
            window.location.reload(1);
         }
      });
  }
}

{% with app_name|add:":status_vm" as url_path %}
var status_url = "{% url url_path operating_system %}";
{% endwith %}
poll_status(status_url, 5000)
