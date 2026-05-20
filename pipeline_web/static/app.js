const overlay = document.querySelector("[data-loading-overlay]");
const loadingMessage = document.querySelector("[data-loading-message]");

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    if (!form.checkValidity()) {
      return;
    }

    const label = form.dataset.loadingLabel || "Working...";
    const submitter = form.querySelector("button[type='submit']");

    document.body.classList.add("is-loading");
    if (overlay) {
      overlay.setAttribute("aria-hidden", "false");
    }
    if (loadingMessage) {
      loadingMessage.textContent = label;
    }
    if (submitter instanceof HTMLButtonElement) {
      submitter.dataset.originalLabel = submitter.textContent.trim();
      submitter.textContent = submitter.dataset.loadingLabel || label;
      submitter.disabled = true;
    }
  });
});

