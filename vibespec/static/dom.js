/* Tiny DOM helpers. Text is always inserted as text nodes; styles only via CSSOM (the CSP forbids inline style attributes). */
const VS = window.VS = {};
VS.el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
};
VS.svg = (tag, attrs = {}, ...kids) => {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
};
VS.$ = (s, r = document) => r.querySelector(s);
VS.ANCHOR_CLASS = ["c0", "c1", "c2"];
VS.ANCHOR_VAR = ["var(--a1)", "var(--a2)", "var(--a3)"];
VS.pct = (v) => `${Math.round(v * 100)}%`;
VS.DOMAINS = [
  { key: "artist", id: "soundscape", cls: "sound", title: "Soundscape", blurb: "Music and atmosphere for the lobby, rooms and events." },
  { key: "book", id: "library", cls: "library", title: "Library", blurb: "Reading and cultural discovery for the shelves and the bedside." },
  { key: "brand", id: "amenities", cls: "amenities", title: "Amenities", blurb: "Brands that fit the stay: bath, linen, minibar and retail." },
  { key: "place", id: "neighborhood", cls: "neighborhood", title: "Neighborhood", blurb: "Local places to send guests, within your constraints." },
];
