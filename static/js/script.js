<script>
function openLogin() {
    document.getElementById("loginModal").style.display = "flex";
}

function loginUser() {
    let mobile = document.getElementById("mobile").value;
    let uname = document.getElementById("uname").value;

    if (mobile.length !== 10) {
        alert("Enter valid mobile number");
        return;
    }

    if (!uname) {
        alert("Enter username");
        return;
    }

    localStorage.setItem("username", uname);
    document.getElementById("username").innerText = uname;
    document.getElementById("loginModal").style.display = "none";
}

window.onload = () => {
    let u = localStorage.getItem("username");
    if (u) {
        document.getElementById("username").innerText = u;
    }
}
</script>
