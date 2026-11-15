// Blind pairwise page for the benchmark: two images, no names; votes go to human_pairs.jsonl.
const token = document.querySelector('meta[name="pw-token"]').content;
const name = new URLSearchParams(location.search).get("b") || "";
const base = `/api/bench/${encodeURIComponent(name)}`;
let pair = null;

async function call(path, body) {
  const init = body ? { method: "POST", headers: { "Content-Type": "application/json", "X-PW-Token": token }, body: JSON.stringify(body) } : {};
  const res = await fetch(base + path, init);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ? data.error.message : res.statusText);
  return data;
}

function show(next) {
  pair = next;
  const box = document.getElementById("pair");
  const left = document.getElementById("left");
  document.querySelectorAll("[data-w]").forEach((b) => { b.disabled = !pair; });
  if (!pair) { box.innerHTML = '<p class="muted">All pairs voted. Thank you.</p>'; left.textContent = ""; return; }
  box.innerHTML = ["a", "b"].map((side, i) => `<figure class="cmp"><img class="px" alt="${i ? "Right" : "Left"} image" src="${base}/img/${pair[side]}"><figcaption>${i ? "Right" : "Left"}</figcaption></figure>`).join("");
  left.textContent = `${pair.left} pair${pair.left === 1 ? "" : "s"} left`;
}

async function vote(winner) {
  if (!pair) return;
  show((await call("/vote", { a: pair.a, b: pair.b, winner })).pair);
}

document.addEventListener("click", (ev) => { const w = ev.target.closest("[data-w]"); if (w) vote(w.dataset.w); });
document.addEventListener("keydown", (ev) => { const w = { 1: "a", 0: "tie", 2: "b" }[ev.key]; if (w) vote(w); });
call("/pair").then((d) => show(d.pair)).catch((err) => { document.getElementById("pair").textContent = err.message; });
