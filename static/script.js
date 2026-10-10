document.addEventListener("DOMContentLoaded", () => {
    const images = document.querySelectorAll("img");
    images.forEach(img => {
        img.addEventListener("error", () => {
            img.style.background = "#e8e5dc";
            img.style.objectFit = "cover";
        });
    });
});
