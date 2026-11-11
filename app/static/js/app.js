// Confirmación de acciones destructivas + notificaciones en tiempo real (alertas de negocio).
document.addEventListener("submit", (e) => {
  const msg = e.target.dataset && e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});

function mostrarToast(titulo, texto, tipo) {
  const cont = document.getElementById("toasts");
  const t = document.createElement("div");
  t.className = "toast toast-" + (tipo || "info");
  const b = document.createElement("strong");
  b.textContent = titulo;
  const p = document.createElement("span");
  p.textContent = texto;
  t.append(b, p);
  cont.appendChild(t);
  setTimeout(() => t.remove(), 8000);
}
window.mostrarToast = mostrarToast;

window.socket = io();
window.socket.on("alerta", (a) => mostrarToast(a.titulo, a.mensaje, a.severidad));
window.socket.on("error_chat", (e) => mostrarToast("Chat", e.mensaje, "warning"));
