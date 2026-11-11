(() => {
  const s = window.socket;
  let salaActual = null;
  const $ = (id) => document.getElementById(id);
  const cajaMsgs = $("mensajes");
  const hora = (iso) => new Date(iso).toLocaleTimeString("es-EC", { hour: "2-digit", minute: "2-digit" });

  function pintar(m) {
    const div = document.createElement("div");
    div.className = "msg";
    const autor = document.createElement("strong");
    autor.textContent = m.usuario;
    const meta = document.createElement("small");
    meta.textContent = " " + hora(m.fecha);
    const texto = document.createElement("p");
    texto.textContent = m.texto; // textContent: evita XSS
    div.append(autor, meta, texto);
    cajaMsgs.appendChild(div);
    cajaMsgs.scrollTop = cajaMsgs.scrollHeight;
  }

  function unirse(id) {
    salaActual = id;
    s.emit("unirse", { sala_id: id });
  }

  document.querySelectorAll(".sala").forEach((b) =>
    b.addEventListener("click", () => unirse(parseInt(b.dataset.sala, 10))));

  s.on("historial", (h) => {
    salaActual = h.sala_id;
    $("sala-actual").textContent = "Sala: " + h.sala;
    cajaMsgs.replaceChildren();
    h.mensajes.forEach(pintar);
    $("texto").disabled = false;
    $("enviar").disabled = false;
    $("texto").focus();
    document.querySelectorAll(".sala").forEach((b) =>
      b.classList.toggle("activa", parseInt(b.dataset.sala, 10) === h.sala_id));
  });

  s.on("mensaje", (m) => { if (m.sala_id === salaActual) pintar(m); });

  s.on("presencia", (lista) => {
    $("n-conectados").textContent = lista.length;
    const ul = $("conectados");
    ul.replaceChildren();
    lista.forEach((n) => { const li = document.createElement("li"); li.textContent = "● " + n; ul.appendChild(li); });
  });

  s.on("connect", () => { if (salaActual) unirse(salaActual); }); // reconexión

  $("form-chat").addEventListener("submit", (e) => {
    e.preventDefault();
    const txt = $("texto").value.trim();
    if (!txt || !salaActual) return;
    s.emit("mensaje", { sala_id: salaActual, texto: txt });
    $("texto").value = "";
  });
})();
