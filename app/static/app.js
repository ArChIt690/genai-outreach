document.querySelectorAll("[data-draft-input]").forEach((input) => {
  input.addEventListener("input", () => {
    const count = document.querySelector("[data-char-count]");
    if (count) count.textContent = input.value.length + " / 800 — save changes before approval";
    document.querySelectorAll("[data-approval-action] button").forEach((button) => {
      button.disabled = true;
    });
  });
});
document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const pressed = event.submitter;
    if (!(pressed && pressed.formNoValidate) && !form.reportValidity()) return;
    const button = pressed || form.querySelector("button[type=submit],button:not([type])");
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    }
  });
});
