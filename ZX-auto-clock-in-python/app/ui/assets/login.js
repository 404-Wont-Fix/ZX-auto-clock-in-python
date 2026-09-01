const form = document.querySelector("#loginForm");
const button = document.querySelector("#loginBtn");
const errorMessage = document.querySelector("#errorMessage");


function showError(message) {
  errorMessage.textContent = message;
  errorMessage.classList.add("show");
}


form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorMessage.classList.remove("show");
  button.disabled = true;
  button.textContent = "正在验证";

  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        username: document.querySelector("#username").value,
        password: document.querySelector("#password").value,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
      throw new Error(data.error || data.detail || "用户名或密码错误");
    }
    localStorage.setItem("auth_token", data.token);
    button.textContent = "登录成功";
    window.setTimeout(() => window.location.assign("/dashboard"), 180);
  } catch (error) {
    showError(error.message || "网络错误，请稍后重试");
    button.disabled = false;
    button.textContent = "登录";
  }
});
