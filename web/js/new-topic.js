/* New-topic form: suggest keywords with the local model, confirm, then start the pipeline. */

const form = document.getElementById("topic-form");
const review = document.getElementById("review");
const keywordList = document.getElementById("keyword-list");
const statusEl = document.getElementById("status");
const suggestButton = document.getElementById("suggest-button");
const confirmButton = document.getElementById("confirm-button");
const cancelButton = document.getElementById("cancel-button");

let pending = null; // { id, name, lookbackDays, keywords }

function setStatus(text) {
  statusEl.textContent = text;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("topic-id").value.trim();
  const name = document.getElementById("topic-name").value.trim();
  const description = document.getElementById("topic-description").value.trim();
  if (!id || !name) return;

  suggestButton.disabled = true;
  setStatus("Asking the local model for keywords...");
  try {
    const response = await fetch("/api/topics/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setStatus(body.error || "Keyword suggestion failed.");
      return;
    }
    const body = await response.json();
    pending = { id, name, keywords: body.keywords || [] };
    keywordList.textContent = pending.keywords.length
      ? pending.keywords.join(", ")
      : "(none suggested; the topic will start with no keywords)";
    form.hidden = true;
    review.hidden = false;
    setStatus("");
  } catch {
    setStatus("Could not reach the desk server.");
  } finally {
    suggestButton.disabled = false;
  }
});

confirmButton.addEventListener("click", async () => {
  if (!pending) return;
  confirmButton.disabled = true;
  setStatus("Creating the topic and starting the pipeline...");
  try {
    const response = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pending),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus(body.error || "Could not create the topic.");
      return;
    }
    setStatus(
      `Started. "${pending.name}" is running in the background; check "This week" shortly.`,
    );
    review.hidden = true;
  } catch {
    setStatus("Could not reach the desk server.");
  } finally {
    confirmButton.disabled = false;
  }
});

cancelButton.addEventListener("click", () => {
  pending = null;
  review.hidden = true;
  form.hidden = false;
  setStatus("");
});
