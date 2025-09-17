document.addEventListener("DOMContentLoaded", function () {
    console.log("✨ Custom Admin JS chargé !");

    // 🔹 Toggle Dark Mode
    let toggleBtn = document.createElement("button");
    toggleBtn.innerHTML = "🌙 / ☀️";
    toggleBtn.id = "darkModeToggle";
    toggleBtn.style.position = "fixed";
    toggleBtn.style.bottom = "20px";
    toggleBtn.style.left = "20px";
    toggleBtn.style.background = "#007bff";
    toggleBtn.style.color = "#fff";
    toggleBtn.style.border = "none";
    toggleBtn.style.borderRadius = "50%";
    toggleBtn.style.width = "50px";
    toggleBtn.style.height = "50px";
    toggleBtn.style.cursor = "pointer";
    toggleBtn.style.fontSize = "20px";
    toggleBtn.style.boxShadow = "0 4px 12px rgba(0,0,0,0.3)";
    document.body.appendChild(toggleBtn);

    // Charger mode enregistré
    if (localStorage.getItem("dark-mode") === "enabled") {
        document.body.classList.add("dark-mode");
    }

    toggleBtn.addEventListener("click", function () {
        document.body.classList.toggle("dark-mode");
        if (document.body.classList.contains("dark-mode")) {
            localStorage.setItem("dark-mode", "enabled");
        } else {
            localStorage.setItem("dark-mode", "disabled");
        }
    });

    // 🔹 Retour en haut
    let backToTop = document.createElement("button");
    backToTop.innerHTML = "⬆";
    backToTop.id = "backToTop";
    document.body.appendChild(backToTop);

    backToTop.style.position = "fixed";
    backToTop.style.bottom = "20px";
    backToTop.style.right = "20px";
    backToTop.style.display = "none";
    backToTop.style.background = "#007bff";
    backToTop.style.color = "#fff";
    backToTop.style.border = "none";
    backToTop.style.borderRadius = "50%";
    backToTop.style.width = "45px";
    backToTop.style.height = "45px";
    backToTop.style.fontSize = "20px";
    backToTop.style.cursor = "pointer";
    backToTop.style.boxShadow = "0 4px 12px rgba(0,0,0,0.2)";

    window.addEventListener("scroll", function () {
        backToTop.style.display = window.scrollY > 200 ? "block" : "none";
    });

    backToTop.addEventListener("click", function () {
        window.scrollTo({ top: 0, behavior: "smooth" });
    });
});
