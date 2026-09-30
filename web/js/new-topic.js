/* New-topic form: suggest keywords with the local model, confirm, then start the pipeline. */

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

const form = document.getElementById("topic-form");
const review = document.getElementById("review");
const keywordList = document.getElementById("keyword-list");
const statusEl = document.getElementById("status");
const suggestButton = document.getElementById("suggest-button");
const confirmButton = document.getElementById("confirm-button");
const cancelButton = document.getElementById("cancel-button");

let pending = null; // { id, name, keywords }

function setStatus(text, tone) {
  statusEl.textContent = text;
  if (tone) statusEl.setAttribute("data-tone", tone);
  else statusEl.removeAttribute("data-tone");
}

function renderKeywords(keywords) {
  if (!keywords.length) {
    keywordList.innerHTML =
      '<li class="keyword-chip" data-empty="true">No keywords suggested; the topic will start with none.</li>';
    return;
  }
  keywordList.innerHTML = keywords
    .map((keyword) => `<li class="keyword-chip">${esc(keyword)}</li>`)
    .join("");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.getElementById("topic-id").value.trim();
  const name = document.getElementById("topic-name").value.trim();
  const description = document.getElementById("topic-description").value.trim();
  if (!id || !name) return;

  suggestButton.disabled = true;
  setStatus("Asking the local model for keywords…");
  try {
    const response = await fetch("/api/topics/suggest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setStatus(body.error || "Keyword suggestion failed.", "error");
      return;
    }
    const body = await response.json();
    pending = { id, name, keywords: body.keywords || [] };
    renderKeywords(pending.keywords);
    form.hidden = true;
    review.hidden = false;
    setStatus("");
  } catch {
    setStatus("Could not reach the desk server.", "error");
  } finally {
    suggestButton.disabled = false;
  }
});

confirmButton.addEventListener("click", async () => {
  if (!pending) return;
  confirmButton.disabled = true;
  setStatus("Creating the topic and starting the pipeline…");
  try {
    const response = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pending),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      setStatus(body.error || "Could not create the topic.", "error");
      return;
    }
    setStatus(
      `Started. "${pending.name}" is running in the background; check "This week" shortly.`,
      "success",
    );
    review.hidden = true;
  } catch {
    setStatus("Could not reach the desk server.", "error");
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
