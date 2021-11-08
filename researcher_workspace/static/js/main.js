// Bootstrap components
var alertMessageList = [].slice.call(document.querySelectorAll('.toast'));
var alertMessages = alertMessageList.map(function (toastEl) {
  return new bootstrap.Toast(toastEl,{
    delay: 5000
  });
});

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

// Custom functions
function scrollToId(elId) {
  document.getElementById(elId).scrollIntoView({
    behavior: 'smooth'
  });
}