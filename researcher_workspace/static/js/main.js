// Bootstrap components
var alertMessageList = [].slice.call(document.querySelectorAll('.toast'));
var alertMessages = alertMessageList.map(function (toastEl) {
  return new bootstrap.Toast(toastEl,{
    delay: 5000
  });
});

var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
  return new bootstrap.Popover(popoverTriggerEl)
})

// Window ready event
window.onload = function() {
  alertMessages.forEach(toast => toast.show()); // Show any alert messages
  if(window.location.hash) { scrollToId(window.location.hash) };
};

// Add smooth scroll to anchors
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
      e.preventDefault();
      scrollToId(this.getAttribute('href'));
  });
});

// removes the focus state on from the buttons that were clicked to launch a modal
document.querySelectorAll(".modal").forEach(modal => {
  var modalButton = {};
  modal.addEventListener("shown.bs.modal", function(e) {
    modalButton = e.relatedTarget;
    modal.addEventListener("hidden.bs.modal", function(e) {
      modalButton.blur(); // Defocus the button that triggered the modal
    });
  });
});

// Does the welcome background exist?
if(document.getElementById("welcome-bg")) {
  // Stop css animations after 1 minute
  setTimeout(function() {
    
    // pause all line animations
    const linesDashed = document.getElementById('lines-dashed');
    for(const path of linesDashed.getElementsByTagName("path")) {
      path.classList.add('paused');
    }
    for(const line of linesDashed.getElementsByTagName("line")) {
      line.classList.add('paused');
    }

    // pause cog animations
    for(const path of document.getElementById('cogs').getElementsByTagName("path")) {
      path.classList.add('paused');
    }

    // pause flashing light animations
    for(const flashingLight of document.getElementsByClassName("flashing-light")) {
      flashingLight.classList.add('paused');
    }
  }, 60000);
}

// Custom functions
function scrollToId(elId) {
  document.getElementById(elId).scrollIntoView({
    behavior: 'smooth'
  });
}
