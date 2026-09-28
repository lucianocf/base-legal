// Base Legal corpus explorer: client-side search over search.json.
// Corpus text is data: rendered with textContent only, never innerHTML.
"use strict";

const input = document.getElementById("q");
const results = document.getElementById("results");
const status = document.getElementById("status");
let index = null;

function fold(text) {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

async function load() {
  if (index) return index;
  const response = await fetch("search.json");
  const items = await response.json();
  index = items.map((item) => ({ ...item, haystack: fold(item.id + " " + item.path + " " + item.text) }));
  return index;
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function search() {
  const terms = fold(input.value).split(/\s+/).filter((t) => t.length > 1);
  results.replaceChildren();
  if (!terms.length) {
    status.textContent = "";
    return;
  }
  const items = await load();
  const found = items.filter((item) => terms.every((t) => item.haystack.includes(t)));
  status.textContent = found.length + " dispositivo(s)" + (found.length > 50 ? "; mostrando 50" : "");
  for (const item of found.slice(0, 50)) {
    const li = el("li");
    const link = el("a", item.id);
    link.href = item.id.split(":")[0] + ".html#" + encodeURIComponent(item.id).replace(/%3A/g, ":");
    li.append(link, el("div", item.path, "path"), el("div", item.text, "text"));
    results.append(li);
  }
}

let timer = null;
input.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(search, 150);
});
document.getElementById("search").addEventListener("submit", (event) => {
  event.preventDefault();
  search();
});
