/* US County Land Index: county finder, chart hover, sortable tables, copy buttons. No dependencies. */
(function () {
  "use strict";
  var base = document.body.getAttribute("data-base") || "";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function money(v) {
    if (v == null) return "n/a";
    if (Math.abs(v - Math.round(v)) < 0.005) return "$" + Math.round(v).toLocaleString("en-US");
    return "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function fold(s) {
    return s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[.']/g, "").replace(/[^a-z0-9]+/g, " ").trim();
  }

  /* ---------------------------------------------------------------- county finder */
  var input = document.getElementById("q");
  if (input) {
    var list = document.getElementById("q-results");
    var index = null, loading = null, active = -1, shown = [];
    var KIND = { c: "census", e: "estimate", i: "estimate", r: "residential land" };
    function load() {
      if (index || loading) return loading;
      loading = fetch(base + "/api/counties.json").then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      }).then(function (rows) {
        index = rows.map(function (r) {
          return { fips: r[0], name: r[1], st: r[2], stName: r[3], path: r[4], v: r[5], y: r[6], k: r[7],
                   key: " " + fold(r[1] + " " + r[3] + " " + r[2]) + " " };
        });
        return index;
      }).catch(function () {
        loading = null;
        render([], "The county list could not be loaded. Browse by state instead.");
      });
      return loading;
    }
    function search(q) {
      var words = fold(q).split(" ").filter(Boolean);
      if (!words.length || !index) return [];
      var out = [];
      for (var i = 0; i < index.length && out.length < 200; i++) {
        var row = index[i], ok = true, score = 0;
        for (var w = 0; w < words.length; w++) {
          var at = row.key.indexOf(" " + words[w]);
          if (at < 0) { ok = false; break; }
          score += at;
        }
        if (ok) out.push([score, row]);
      }
      out.sort(function (a, b) { return a[0] - b[0] || (a[1].name < b[1].name ? -1 : 1); });
      return out.slice(0, 12).map(function (x) { return x[1]; });
    }
    function render(rows, empty) {
      list.textContent = "";
      shown = rows;
      active = -1;
      if (!rows.length) {
        if (empty) { var li = el("li", "none", empty); list.appendChild(li); list.hidden = false; }
        else list.hidden = true;
        input.setAttribute("aria-expanded", empty ? "true" : "false");
        return;
      }
      rows.forEach(function (r, i) {
        var li = el("li");
        var a = el("a");
        a.href = base + r.path;
        a.id = "q-opt-" + i;
        a.setAttribute("role", "option");
        a.appendChild(el("strong", null, r.name + ", " + r.stName));
        if (r.v != null) a.appendChild(el("span", null, money(r.v) + "/acre, " + r.y + " " + (KIND[r.k] || "")));
        li.appendChild(a);
        list.appendChild(li);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }
    function update() {
      var q = input.value;
      if (!q.trim()) { render([]); return; }
      var p = load();
      if (index) render(search(q), "No county matches “" + q.trim() + "”.");
      else if (p) p.then(function () { if (input.value === q) render(search(q), "No county matches “" + q.trim() + "”."); });
    }
    function move(d) {
      if (!shown.length) return;
      active = (active + d + shown.length) % shown.length;
      var links = list.querySelectorAll("a");
      for (var i = 0; i < links.length; i++) links[i].classList.toggle("on", i === active);
      input.setAttribute("aria-activedescendant", "q-opt-" + active);
      links[active].scrollIntoView({ block: "nearest" });
    }
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    list.setAttribute("role", "listbox");
    input.addEventListener("focus", load);
    input.addEventListener("input", update);
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        var pick = shown[active >= 0 ? active : 0];
        if (pick) { e.preventDefault(); window.location.href = base + pick.path; }
      } else if (e.key === "Escape") { render([]); }
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest || !e.target.closest(".finder")) render([]);
    });
  }

  /* ---------------------------------------------------------------- chart hover */
  var NS = "http://www.w3.org/2000/svg";
  Array.prototype.forEach.call(document.querySelectorAll(".chart-wrap[data-chart]"), function (wrap) {
    var d;
    try { d = JSON.parse(wrap.getAttribute("data-chart")); } catch (err) { return; }
    var svg = wrap.querySelector("svg"), layer = svg.querySelector("g.hover"), tip = wrap.querySelector(".tip");
    var years = d.years, first = years[0], last = years[years.length - 1], cur = -1;
    function xOf(y) { return last > first ? d.x0 + (d.x1 - d.x0) * (y - first) / (last - first) : (d.x0 + d.x1) / 2; }
    function yOf(v) { return d.y0 + (d.y1 - d.y0) * (1 - v / d.top); }
    function show(i) {
      if (i < 0 || i >= years.length) return;
      cur = i;
      while (layer.firstChild) layer.removeChild(layer.firstChild);
      var x = xOf(years[i]);
      var line = document.createElementNS(NS, "line");
      line.setAttribute("class", "cross");
      line.setAttribute("x1", x); line.setAttribute("x2", x);
      line.setAttribute("y1", d.y0); line.setAttribute("y2", d.y1);
      layer.appendChild(line);
      tip.textContent = "";
      tip.appendChild(el("b", null, String(years[i])));
      d.series.forEach(function (s) {
        var v = s.v[i];
        if (v == null) return;
        var c = document.createElementNS(NS, "circle");
        c.setAttribute("class", "mk s" + s.slot);
        c.setAttribute("cx", x); c.setAttribute("cy", yOf(v)); c.setAttribute("r", 4.5);
        layer.appendChild(c);
        var row = el("div");
        row.appendChild(el("i", "s" + s.slot));
        row.appendChild(el("strong", null, money(v)));
        row.appendChild(el("span", null, s.name + (s.k[i] ? " (" + s.k[i] + ")" : "")));
        tip.appendChild(row);
      });
      tip.hidden = false;
      var box = svg.getBoundingClientRect(), scale = box.width / d.w;
      var px = x * scale, w = tip.offsetWidth;
      var left = px + 14 + w > box.width ? px - 14 - w : px + 14;
      tip.style.left = Math.max(0, left) + "px";
      tip.style.top = Math.max(0, d.y0 * scale) + "px";
    }
    function hide() {
      cur = -1;
      tip.hidden = true;
      while (layer.firstChild) layer.removeChild(layer.firstChild);
    }
    function nearest(clientX) {
      var box = svg.getBoundingClientRect();
      var x = (clientX - box.left) * d.w / box.width;
      var best = 0, dist = Infinity;
      for (var i = 0; i < years.length; i++) {
        var dd = Math.abs(xOf(years[i]) - x);
        if (dd < dist) { dist = dd; best = i; }
      }
      return best;
    }
    svg.addEventListener("pointermove", function (e) { show(nearest(e.clientX)); });
    svg.addEventListener("pointerdown", function (e) { show(nearest(e.clientX)); });
    svg.addEventListener("pointerleave", hide);
    wrap.addEventListener("focus", function () { show(years.length - 1); });
    wrap.addEventListener("blur", hide);
    wrap.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); show(Math.max(0, (cur < 0 ? years.length : cur) - 1)); }
      else if (e.key === "ArrowRight") { e.preventDefault(); show(Math.min(years.length - 1, cur + 1)); }
      else if (e.key === "Home") { e.preventDefault(); show(0); }
      else if (e.key === "End") { e.preventDefault(); show(years.length - 1); }
      else if (e.key === "Escape") { hide(); }
    });
    wrap.setAttribute("aria-label", (svg.getAttribute("aria-label") || "Chart") + ". Use the left and right arrow keys to read each year.");
  });

  /* ---------------------------------------------------------------- sortable tables */
  Array.prototype.forEach.call(document.querySelectorAll("table.sortable"), function (table) {
    var heads = table.querySelectorAll("thead th");
    Array.prototype.forEach.call(heads, function (th, col) {
      if (th.classList.contains("nosort")) return;
      th.tabIndex = 0;
      th.setAttribute("role", "columnheader button");
      function sort() {
        var dir = th.getAttribute("aria-sort") === "descending" ? "ascending" : "descending";
        if (!th.hasAttribute("aria-sort") && !th.classList.contains("n")) dir = "ascending";
        Array.prototype.forEach.call(heads, function (h) { h.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", dir);
        var body = table.tBodies[0], rows = Array.prototype.slice.call(body.rows), sign = dir === "ascending" ? 1 : -1;
        rows.sort(function (a, b) {
          var ca = a.cells[col], cb = b.cells[col];
          var va = ca.getAttribute("data-v"), vb = cb.getAttribute("data-v");
          if (va !== null && vb !== null) {
            if (va === "" && vb === "") return 0;
            if (va === "") return 1;
            if (vb === "") return -1;
            return sign * (parseFloat(va) - parseFloat(vb));
          }
          return sign * ca.textContent.localeCompare(cb.textContent);
        });
        rows.forEach(function (r) { body.appendChild(r); });
      }
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    });
  });

  /* ---------------------------------------------------------------- copy buttons */
  Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"), function (box) {
    if (!navigator.clipboard) return;
    var text = box.textContent;
    var b = el("button", null, "Copy");
    b.type = "button";
    b.addEventListener("click", function () {
      navigator.clipboard.writeText(text).then(function () {
        b.textContent = "Copied";
        setTimeout(function () { b.textContent = "Copy"; }, 1800);
      });
    });
    box.appendChild(b);
  });
})();
