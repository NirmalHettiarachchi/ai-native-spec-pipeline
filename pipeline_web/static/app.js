const overlay = document.querySelector("[data-loading-overlay]");
const loadingMessage = document.querySelector("[data-loading-message]");
let loadingTimeout = null;

function setLoading(isLoading, label = "Working...", submitter = null) {
  if (loadingTimeout) {
    window.clearTimeout(loadingTimeout);
    loadingTimeout = null;
  }

  if (!isLoading) {
    document.body.classList.remove("is-loading");
    if (overlay) {
      overlay.setAttribute("aria-hidden", "true");
    }
    if (loadingMessage) {
      loadingMessage.textContent = "Working...";
    }
    document.querySelectorAll("[data-loading-active='true']").forEach((button) => {
      if (button instanceof HTMLButtonElement) {
        if (button.dataset.originalHtml) {
          button.innerHTML = button.dataset.originalHtml;
        }
        if (button.dataset.wasDisabled === "false") {
          button.disabled = false;
        }
        delete button.dataset.originalHtml;
        delete button.dataset.wasDisabled;
        delete button.dataset.loadingActive;
      }
    });
    return;
  }

  document.body.classList.add("is-loading");
  if (overlay) {
    overlay.setAttribute("aria-hidden", "false");
  }
  if (loadingMessage) {
    loadingMessage.textContent = label;
  }
  if (submitter instanceof HTMLButtonElement) {
    submitter.dataset.originalHtml = submitter.innerHTML;
    submitter.dataset.wasDisabled = submitter.disabled ? "true" : "false";
    submitter.dataset.loadingActive = "true";
    submitter.textContent = submitter.dataset.loadingLabel || label;
    submitter.disabled = true;
  }

  loadingTimeout = window.setTimeout(() => {
    setLoading(false);
  }, 15000);
}

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!form.checkValidity()) {
      return;
    }

    const label = form.dataset.loadingLabel || "Working...";
    const submitter = event.submitter instanceof HTMLButtonElement ? event.submitter : null;
    setLoading(true, label, submitter);
  });
});

document.querySelectorAll("[data-spec-source-form]").forEach((form) => {
  const choices = form.querySelectorAll("[data-spec-source-choice]");
  const panels = form.querySelectorAll("[data-spec-source-panel]");

  function syncSpecSource() {
    const selected = form.querySelector("[data-spec-source-choice]:checked");
    const selectedSource = selected ? selected.value : "repository";

    panels.forEach((panel) => {
      const isActive = panel.dataset.specSourcePanel === selectedSource;
      panel.hidden = !isActive;
      panel.querySelectorAll("input, select").forEach((control) => {
        control.disabled = !isActive;
        if (control instanceof HTMLInputElement && control.type === "file") {
          control.required = isActive;
        }
        if (control instanceof HTMLSelectElement) {
          control.required = isActive;
        }
      });
    });
  }

  choices.forEach((choice) => {
    choice.addEventListener("change", syncSpecSource);
  });
  syncSpecSource();
});

window.addEventListener("pageshow", () => {
  setLoading(false);
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    setLoading(false);
  }
});

if (window.lucide) {
  window.lucide.createIcons({
    attrs: {
      "aria-hidden": "true",
    },
  });
}
