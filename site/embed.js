/* Embeddable county card: /embed/?fips=19169. Reads the county's static JSON and draws a small card. */
(function () {
  "use strict";
  var base = document.body.getAttribute("data-base") || "";
  var card = document.getElementById("card");
  var fips = (new URLSearchParams(window.location.search).get("fips") || "").trim();

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function money(v) {
    return v == null ? "n/a" : "$" + Math.round(v).toLocaleString("en-US");
  }
  function fail(msg) {
    card.textContent = "";
    card.appendChild(el("p", null, msg));
    var a = el("a", null, "Open the US County Land Index");
    a.href = base + "/";
    a.target = "_top";
    card.appendChild(a);
  }
  if (!/^\d{5}$/.test(fips)) { fail("No county selected."); return; }

  fetch(base + "/api/county/" + fips + ".json").then(function (r) {
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }).then(function (c) {
    card.textContent = "";
    var h = el("h1");
    var link = el("a", null, c.name + ", " + c.state_name);
    link.href = c.url;
    link.target = "_top";
    h.appendChild(link);
    card.appendChild(h);
    var s = c.usda_farm_real_estate_per_acre || [];
    if (s.length) {
      var last = s[s.length - 1];
      card.appendChild(el("p", "tl", "Farm real estate, " + last.year + (last.kind === "census" ? " census" : " estimate")));
      var v = el("p", "tv", money(last.value));
      v.appendChild(el("span", "per", " per acre"));
      card.appendChild(v);
      if (s.length > 2) {
        var lo = Infinity, hi = -Infinity;
        s.forEach(function (p) { lo = Math.min(lo, p.value); hi = Math.max(hi, p.value); });
        var span = (hi - lo) || 1, w = 300, hgt = 44, pts = [];
        s.forEach(function (p, i) {
          pts.push((2 + (w - 4) * i / (s.length - 1)).toFixed(1) + "," + (2 + (hgt - 4) * (1 - (p.value - lo) / span)).toFixed(1));
        });
        var NS = "http://www.w3.org/2000/svg";
        var svg = document.createElementNS(NS, "svg");
        svg.setAttribute("class", "spark");
        svg.setAttribute("viewBox", "0 0 " + w + " " + hgt);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.setAttribute("aria-hidden", "true");
        var path = document.createElementNS(NS, "path");
        path.setAttribute("d", "M" + pts.join("L"));
        path.setAttribute("vector-effect", "non-scaling-stroke");
        svg.appendChild(path);
        card.appendChild(svg);
        card.appendChild(el("p", "ts", s[0].year + " to " + last.year + ": " + money(s[0].value) + " to " + money(last.value) + " per acre"));
      }
    } else if (c.fhfa_residential_land && c.fhfa_residential_land.length) {
      var f = c.fhfa_residential_land[c.fhfa_residential_land.length - 1];
      card.appendChild(el("p", "tl", "Residential land, " + f.year + " (FHFA)"));
      var fv = el("p", "tv", money(f.land_value_per_acre));
      fv.appendChild(el("span", "per", " per acre"));
      card.appendChild(fv);
    } else {
      card.appendChild(el("p", null, "No published land value for this county."));
    }
    card.appendChild(el("p", "src", "USDA NASS and FHFA data via the US County Land Index. Not investment advice."));
  }).catch(function () { fail("This county could not be loaded."); });
})();
