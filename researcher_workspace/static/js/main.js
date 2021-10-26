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
};

// Add smooth scroll to anchors
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
      e.preventDefault();
      console.log(this.getAttribute('href'));
      document.getElementById(this.getAttribute('href')).scrollIntoView({
          behavior: 'smooth'
      });
  });
});