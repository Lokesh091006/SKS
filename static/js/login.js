function openLogin() {
    document.getElementById("loginModal").style.display = "flex";
}

function loginUser() {
    let mobile = document.getElementById("mobile").value;
    let uname = document.getElementById("uname").value;

    if (mobile.length !== 10) {
        alert("Enter valid 10 digit mobile number");
        return;
    }

    if (uname === "") {
        alert("Enter username");
        return;
    }

    document.getElementById("username").innerText = uname;
    document.getElementById("loginModal").style.display = "none";
}
