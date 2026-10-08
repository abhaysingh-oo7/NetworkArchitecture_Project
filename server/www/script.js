const button = document.getElementById("statusButton");
const status = document.getElementById("status");

button.addEventListener("click", () => {
    status.textContent = "Frontend is working. The page came from the custom server.";
});
