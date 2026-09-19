// Filters the catalog in the browser. No framework, no network beyond
// index.json, so a copy of this directory works offline.

const CONTROLS = ["q", "year", "type", "degree", "topic", "code", "slides"];

let entries = [];

function escape(text) {
  const box = document.createElement("div");
  box.textContent = text == null ? "" : String(text);
  return box.innerHTML.replace(/"/g, "&quot;");
}

function value(id) {
  const node = document.getElementById(id);
  return node.type === "checkbox" ? node.checked : node.value.trim().toLowerCase();
}

function matches(e, f) {
  if (f.year && String(e.year) !== f.year) return false;
  if (f.type && e.type !== f.type) return false;
  if (f.degree && e.degree !== f.degree) return false;
  if (f.topic && !e.topics.includes(f.topic)) return false;
  if (f.code && !e.has_code) return false;
  if (f.slides && !e.has_slides) return false;
  if (!f.q) return true;

  const haystack = [e.title, e.authors.join(" "), e.summary, e.programme, e.venue,
                    e.topics.join(" "), e.keywords.join(" ")]
    .join(" ").toLowerCase();
  return haystack.includes(f.q);
}

function badge(e) {
  if (e.score == null) return "";
  const honours = e.honours ? " &middot; Matrícula de Honor" : "";
  const cls = e.honours ? "score honours" : "score";
  return `<span class="${cls}">${escape(e.score)} / 10${honours}</span>`;
}

function card(e) {
  const kind = e.degree || e.venue;
  const kindBit = kind ? ` &middot; ${escape(kind)}` : "";
  const topics = e.topics.map((t) =>
    `<a href="?topic=${encodeURIComponent(t)}">${escape(t)}</a>`).join("");

  return `<li>
    <a href="${escape(e.url)}">${escape(e.title)}</a>
    <p class="meta">${escape(e.authors.join(", "))} &middot; ${escape(e.year)}${kindBit}</p>
    ${badge(e)}
    <p>${escape(e.summary)}</p>
    <p class="topics">${topics}</p>
  </li>`;
}

function render() {
  const f = {};
  CONTROLS.forEach((id) => { f[id] = value(id); });

  const shown = entries.filter((e) => matches(e, f));
  document.getElementById("results").innerHTML = shown.map(card).join("");
  document.getElementById("count").textContent =
    `${shown.length} of ${entries.length} entries`;
}

fetch("index.json")
  .then((response) => response.json())
  .then((data) => {
    entries = data;

    // A topic link (from a card or an entry page) arrives as ?topic=...
    const topic = new URLSearchParams(location.search).get("topic");
    if (topic) document.getElementById("topic").value = topic;

    CONTROLS.forEach((id) => {
      document.getElementById(id).addEventListener("input", render);
    });
    render();
  })
  .catch(() => {
    document.getElementById("count").textContent = "Catalog could not be loaded";
  });
