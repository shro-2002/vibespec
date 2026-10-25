/* Guided form: anchor chips, example fill, validation, request body. */
(() => {
  const { el, $ } = VS;
  const MAX_ANCHORS = 3, SUGGESTIONS = ["Muji", "Patagonia", "Aesop", "IKEA", "Carhartt", "Lululemon"];
  const EXAMPLE = {
    concept: "Minimalist, eco-conscious 40-room boutique hotel for mindful travellers", city: "New York City",
    anchors: ["Muji", "Patagonia"], goals: "Calm minimalist sound, a small library of nature and sustainability books, natural low-waste amenities, local places to explore on foot",
    max_place_price_level: "3", min_place_rating: "4.0", min_book_year: "2012", amenity_unit_budget_usd: "30", exclude_terms: "Starbucks", hotel_location: "40.7223, -73.9874",
  };
  const form = $("#f"), box = $("#chips"), input = $("#anchor-in"), err = $("#anchor-err");
  let anchors = [];
  VS.confirmed = {};

  function draw() {
    box.querySelectorAll(".chip").forEach((c) => c.remove());
    anchors.forEach((name, i) => box.insertBefore(el("span", { class: `chip ${VS.ANCHOR_CLASS[i]}` }, name,
      el("button", { type: "button", "aria-label": `Remove ${name}`, onclick: () => { anchors.splice(i, 1); draw(); input.focus(); } }, "×")), input));
    input.disabled = anchors.length >= MAX_ANCHORS;
    input.placeholder = anchors.length >= MAX_ANCHORS ? "Three anchors is the maximum" : "Type a brand, press Enter";
    $("#suggest").querySelectorAll("button").forEach((b) => { b.disabled = anchors.includes(b.textContent) || anchors.length >= MAX_ANCHORS; b.style.opacity = b.disabled ? ".4" : ""; });
  }
  function add(raw) {
    const name = raw.trim().replace(/\s+/g, " ");
    if (!name) return;
    err.textContent = "";
    if (anchors.some((a) => a.toLowerCase() === name.toLowerCase())) { err.textContent = `${name} is already added.`; return; }
    if (anchors.length >= MAX_ANCHORS) { err.textContent = "Three anchors is the maximum."; return; }
    anchors.push(name); input.value = ""; draw();
  }
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(input.value); }
    else if (e.key === "Backspace" && !input.value && anchors.length) { anchors.pop(); draw(); }
  });
  input.addEventListener("blur", () => add(input.value));
  SUGGESTIONS.forEach((s) => $("#suggest").append(el("button", { type: "button", onclick: () => add(s) }, s)));

  function setAll(values) {
    for (const [k, v] of Object.entries(values)) if (k !== "anchors" && form.elements[k]) form.elements[k].value = v;
    anchors = [...values.anchors]; VS.confirmed = {}; draw(); showLocation();
    if (values.max_place_price_level) $("details.opt").open = true;
  }
  /* Precise hotel location: pasted coordinates or a map link, parsed locally. No geocoding service is called. */
  const locIn = $("#hotel_location"), locOut = $("#loc-status");
  const LOC_PATTERNS = [/@(-?\d+\.\d+),(-?\d+\.\d+)/, /!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/, /[?&](?:ll|q|query|sll)=(-?\d+\.\d+),\s*(-?\d+\.\d+)/,
    /mlat=(-?\d+\.\d+)&mlon=(-?\d+\.\d+)/, /#map=\d+\/(-?\d+\.\d+)\/(-?\d+\.\d+)/, /^\s*(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})\s*$/];
  function parseLocation(text) {
    for (const re of LOC_PATTERNS) {
      const m = re.exec(text || "");
      if (m) { const lat = +m[1], lon = +m[2]; if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180) return [lat, lon]; }
    }
    return null;
  }
  let hotelLoc = null;
  function showLocation() {
    const raw = locIn.value.trim();
    hotelLoc = raw ? parseLocation(raw) : null;
    locOut.className = "loc-status" + (raw ? (hotelLoc ? " ok" : " bad") : "");
    if (!raw) { locOut.textContent = "No precise location: places will be city-level leads."; return; }
    if (!hotelLoc) { locOut.textContent = "Could not read a location. Paste coordinates with at least 3 decimals (40.722, -73.987) or a map link."; return; }
    const [lat, lon] = hotelLoc.map((v) => +v.toFixed(5));
    locOut.replaceChildren(`Precise location set: ${lat}, ${lon}. `, el("a", { href: `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`, target: "_blank", rel: "noopener" }, "Check it on OpenStreetMap"));
  }
  locIn.addEventListener("input", showLocation);
  $("#geo").addEventListener("click", () => {
    if (!navigator.geolocation) { locOut.textContent = "This browser cannot share its location. Paste coordinates instead."; return; }
    locOut.textContent = "Asking the browser for this device's location. Use this only if you are at the property.";
    navigator.geolocation.getCurrentPosition((pos) => { locIn.value = `${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}`; showLocation(); },
      () => { locOut.className = "loc-status bad"; locOut.textContent = "Location permission was not given. Paste coordinates or a map link instead."; }, { timeout: 10000 });
  });
  $("#loc-example").addEventListener("click", () => { locIn.value = "40.7223, -73.9874"; showLocation(); });
  showLocation();

  VS.form = {
    fillExample: () => setAll(EXAMPLE),
    body() {
      add(input.value);
      const v = (n) => form.elements[n].value.trim();
      return { concept: v("concept"), city: v("city"), anchors: [...anchors], goals: v("goals"), confirmed: VS.confirmed,
        constraints: Object.fromEntries(["max_place_price_level", "min_place_rating", "min_book_year", "amenity_unit_budget_usd", "exclude_terms"].map((k) => [k, v(k) || null]).concat([["hotel_location", hotelLoc ? hotelLoc.join(", ") : null]])) };
    },
    validate() {
      const b = VS.form.body(), problems = [];
      if (!b.concept) problems.push(["concept", "Describe your hotel in a sentence."]);
      if (!b.city) problems.push(["city", "Enter the city to search places in."]);
      if (locIn.value.trim() && !hotelLoc) problems.push(["hotel_location", "Fix or clear the hotel location."]);
      if (b.anchors.length < 2) { err.textContent = "Add at least two anchors (brands your guests love)."; problems.push(["anchor-in", err.textContent]); }
      $("#form-err").textContent = problems.filter(([id]) => id !== "anchor-in").map(([, m]) => m).join(" ");
      if (problems.length) $(`#${problems[0][0]}`).focus();
      return !problems.length;
    },
    summary: () => { const b = VS.form.body(); return `${b.city}. Anchors: ${b.anchors.join(", ")}.`; },
  };
  $("#fill").addEventListener("click", VS.form.fillExample);
  draw();
})();
