// Base Legal UI. Every piece of text from the API (model output, corpus text)
// is rendered with textContent, never innerHTML (docs/THREAT_MODEL.md S11).
"use strict";

const form = document.getElementById("form");
const question = document.getElementById("question");
const statusBox = document.getElementById("status");
const result = document.getElementById("result");
let mode = "ask";

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

// The official text, with each cross-reference as a link that opens the cited
// provision below it. Offsets count code points (as in Python), so the text is
// sliced as an array of code points, not UTF-16 units.
function linkedText(provision) {
  const quote = el("blockquote");
  const chars = Array.from(provision.text);
  const refs = (provision.references || []).slice().sort((a, b) => a.start - b.start);
  let at = 0;
  for (const ref of refs) {
    if (ref.start < at || ref.end > chars.length) continue;
    quote.append(document.createTextNode(chars.slice(at, ref.start).join("")));
    const link = el("a", chars.slice(ref.start, ref.end).join(""), "xref");
    link.href = "#" + encodeURIComponent(ref.target);
    link.title = ref.target;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      toggleCited(quote, ref.target);
    });
    quote.append(link);
    at = ref.end;
  }
  quote.append(document.createTextNode(chars.slice(at).join("")));
  return quote;
}

async function toggleCited(quote, id) {
  const open = quote.nextElementSibling;
  if (open && open.classList.contains("cited")) {
    open.remove();
    if (open.dataset.id === id) return;
  }
  const box = el("div", "Carregando " + id + "…", "cited");
  box.dataset.id = id;
  quote.after(box);
  try {
    const response = await fetch("/provisions/" + encodeURIComponent(id));
    const data = await response.json();
    box.replaceChildren();
    if (!response.ok) {
      box.append(el("p", id + ": dispositivo indisponível.", "missing"));
      return;
    }
    box.append(el("strong", data.provision.id), el("div", data.provision.path, "path"));
    box.append(linkedText(data.provision));
  } catch (error) {
    box.textContent = "Falha de conexão com o servidor local.";
  }
}

function provisionItem(provision, label) {
  const item = el("li");
  item.append(el("strong", (label ? label + " " : "") + provision.id));
  item.append(el("div", provision.path, "path"));
  item.append(linkedText(provision));
  return item;
}

function renderAnswer(data) {
  if (data.status === "answered") {
    const numbers = new Map(data.provisions.map((p, i) => [p.id, i + 1]));
    const answer = el("p", undefined, "answer");
    for (const part of data.parts) {
      answer.append(document.createTextNode(part.text));
      for (const citation of part.citations) {
        const n = numbers.get(citation.provision_id);
        if (n !== undefined) answer.append(el("sup", "[" + n + "]"));
      }
    }
    result.append(answer, el("h2", "Fontes (texto oficial)"));
    const list = el("ol", undefined, "provisions");
    data.provisions.forEach((p, i) => list.append(provisionItem(p, "[" + (i + 1) + "]")));
    result.append(list);
  } else {
    result.append(el("p", "Sem base no corpus: " + (data.message || ""), "refusal"));
    for (const ref of data.missing_references || []) {
      result.append(el("p", ref + " não existe no corpus.", "missing"));
    }
    if (data.provisions && data.provisions.length) {
      result.append(el("h2", "Dispositivos mais próximos (texto oficial)"));
      const list = el("ul", undefined, "provisions");
      data.provisions.forEach((p) => list.append(provisionItem(p)));
      result.append(list);
    }
  }
}

function renderSearch(data) {
  if (data.refusal) result.append(el("p", "Aviso: " + data.refusal, "refusal"));
  for (const ref of data.missing_references) {
    result.append(el("p", ref + " não existe no corpus.", "missing"));
  }
  const list = el("ol", undefined, "provisions");
  data.hits.forEach((hit) => list.append(provisionItem(hit.provision)));
  result.append(list);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  mode = event.submitter && event.submitter.dataset.mode === "search" ? "search" : "ask";
  result.replaceChildren();
  statusBox.textContent = "Consultando…";
  try {
    const response = await fetch("/" + mode, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question.value }),
    });
    const data = await response.json();
    statusBox.textContent = "";
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "pergunta inválida";
      statusBox.textContent = "Erro " + response.status + ": " + detail;
      return;
    }
    if (data.redactions && Object.keys(data.redactions).length) {
      statusBox.textContent = "Dados pessoais removidos antes do envio: " +
        Object.entries(data.redactions).map(([k, v]) => k + " × " + v).join(", ");
    }
    if (mode === "ask") renderAnswer(data); else renderSearch(data);
    document.getElementById("disclaimer").textContent = data.disclaimer;
  } catch (error) {
    statusBox.textContent = "Falha de conexão com o servidor local.";
  }
});
