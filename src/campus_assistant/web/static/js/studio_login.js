const form = document.getElementById("studioLoginForm");
const passwordInput = document.getElementById("studioPassword");
const toast = document.getElementById("loginToast");

function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.clearTimeout(notify._timer);
  notify._timer = window.setTimeout(() => toast.classList.remove("show"), 2500);
}

async function login(event) {
  event.preventDefault();
  const password = passwordInput.value.trim();
  if (!password) {
    notify("Enter password.");
    return;
  }

  try {
    const response = await fetch("/api/studio/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "Login failed");
    }
    window.location.href = "/studio";
  } catch (error) {
    notify(error.message);
  }
}

form.addEventListener("submit", login);
