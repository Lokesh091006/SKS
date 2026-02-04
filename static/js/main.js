function buyNow(pid) {
  fetch("/check-login")
    .then(res => res.json())
    .then(data => {
      if (data.logged_in) {
        window.location.href = "/order/" + pid;
      } else {
        document.getElementById("nextUrl").value = "/order/" + pid;
        document.getElementById("otpModal").style.display = "flex";
      }
    });
}

// Later:
// Add to cart
// Update quantity
// Payment integration
