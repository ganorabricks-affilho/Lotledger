function wireBusy(formId, btnId, statusId, busyLabel) {
  const form = document.getElementById(formId);
  if (!form) return;
  const btn = document.getElementById(btnId);
  const status = document.getElementById(statusId);
  form.addEventListener("submit", () => {
    btn.disabled = true;
    btn.textContent = busyLabel;
    status.hidden = false;
    document.body.classList.add("is-busy");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form.sync-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.dataset.confirm;
      if (message && !window.confirm(message)) {
        event.preventDefault();
        return;
      }
      const button = form.querySelector("button");
      if (button) {
        button.disabled = true;
        if (form.dataset.busy) button.textContent = form.dataset.busy;
      }
      const status = form.querySelector(".import-status");
      if (status) status.hidden = false;
      if (form.dataset.pageBusy === "1") document.body.classList.add("is-busy");
    });
  });
});
