// Filters the catalog in the browser. No framework, no network beyond
// index.json, so a copy of this directory works offline.

const CONTROLS = ["q", "year", "degree", "kind", "topic", "code", "data"];

// The two halves of the catalog; the first is the default group.
const GROUPS = ["thesis", "publication"];

// Date is the index.json order, newest first; title is the reader's ask.
const SORTS = ["date", "title"];

let entries = [];
let sort = "date";

// The active group lives in the URL, so shared links and topic clicks
// land on the same half. A pre-split ?type=... link names a group too.
const params = new URLSearchParams(location.search);
const wanted = params.get("group") || params.get("type");
let group = GROUPS.includes(wanted) ? wanted : GROUPS[0];

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
  if (e.type !== group) return false;
  if (f.year && String(e.year) !== f.year) return false;
  if (f.degree && e.degree !== f.degree) return false;
  if (f.kind && e.kind !== f.kind) return false;
  if (f.topic && !e.topics.includes(f.topic)) return false;
  if (f.code && !e.has_code) return false;
  if (f.data && !e.has_data) return false;
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

// A thesis is identified by its degree; a paper by its kind and venue.
function kindBit(e) {
  const bits = (e.type === "thesis" ? [e.degree] : [e.kind, e.venue]).filter(Boolean);
  return bits.length ? ` &middot; ${bits.map(escape).join(" &middot; ")}` : "";
}

function card(e) {
  const topics = e.topics.map((t) =>
    `<a href="?group=${encodeURIComponent(group)}&topic=${encodeURIComponent(t)}">${escape(t)}</a>`).join("");

  return `<li>
    <a href="${escape(e.url)}">${escape(e.title)}</a>
    <p class="meta">${escape(e.authors.join(", "))} &middot; ${escape(e.year)}${kindBit(e)}</p>
    ${badge(e)}
    <p>${escape(e.summary)}</p>
    <p class="topics">${topics}</p>
  </li>`;
}

function showGroupControls() {
  GROUPS.forEach((g) => {
    document.getElementById(`group-${g}`).classList.toggle("active", g === group);
  });

  // A facet of one group says nothing in the other.
  document.getElementById("degree").hidden = group !== "thesis";
  document.getElementById("kind").hidden = group !== "publication";
}

function sorted(shown) {
  if (sort === "title") {
    return shown.slice().sort((a, b) =>
      a.title.localeCompare(b.title, undefined, { sensitivity: "base" }));
  }
  return shown;
}

function setSort(next) {
  sort = next;
  SORTS.forEach((k) => {
    document.getElementById(`sort-${k}`).classList.toggle("active", k === next);
  });
  render();
}

function render() {
  const f = {};
  CONTROLS.forEach((id) => {
    const node = document.getElementById(id);
    // A hidden facet belongs to the other group: it must not filter.
    f[id] = node.hidden ? "" : value(id);
  });

  const inGroup = entries.filter((e) => e.type === group);
  const shown = sorted(inGroup.filter((e) => matches(e, f)));
  document.getElementById("results").innerHTML = shown.map(card).join("");
  document.getElementById("count").textContent =
    `${shown.length} of ${inGroup.length} entries`;
}

function setGroup(next) {
  group = next;

  // replaceState, not a navigation: the catalog is already loaded.
  const url = new URL(location);
  url.searchParams.set("group", next);
  history.replaceState(null, "", url);

  showGroupControls();
  render();
}

fetch("index.json")
  .then((response) => response.json())
  .then((data) => {
    entries = data;

    // A topic link (from a card or an entry page) arrives as ?topic=...
    const topic = params.get("topic");
    if (topic) document.getElementById("topic").value = topic;

    CONTROLS.forEach((id) => {
      document.getElementById(id).addEventListener("input", render);
    });
    GROUPS.forEach((g) => {
      document.getElementById(`group-${g}`).addEventListener("click", () => setGroup(g));
    });
    SORTS.forEach((k) => {
      document.getElementById(`sort-${k}`).addEventListener("click", () => setSort(k));
    });

    showGroupControls();
    render();
  })
  .catch(() => {
    document.getElementById("count").textContent = "Catalog could not be loaded";
  });
