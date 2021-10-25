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