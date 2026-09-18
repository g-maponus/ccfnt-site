/* CCFNT — "Prochaine Messe" widget.
   Renders the next upcoming mass + live countdown from the admin-managed
   schedule (/api/masses → masses.json). Replaces the old hardcoded date array
   so admin "Dates de messe" edits are reflected everywhere automatically. */
(function () {
  var moisFr = ['Janvier','Février','Mars','Avril','Mai','Juin',
                'Juillet','Août','Septembre','Octobre','Novembre','Décembre'];

  function render(dates) {
    var w = document.getElementById('milestone_widget-2-content');
    if (!w) return;
    var today = new Date(); today.setHours(0, 0, 0, 0);
    var next = null;
    for (var i = 0; i < dates.length; i++) {
      if (dates[i] >= today) { next = dates[i]; break; }
    }
    if (!next) {
      w.innerHTML = '<p style="text-align:center;color:#666">Aucune messe prévue.</p>';
      return;
    }
    var diff = Math.round((next - today) / 86400000);
    var label = diff === 0 ? "C'est aujourd'hui !" : diff === 1 ? 'jour restant' : 'jours restants';
    w.innerHTML =
      '<div style="text-align:center;font-family:Helvetica,Arial,sans-serif;padding:4px 0 8px">' +
        '<div class="ccfnt-cal-tile" style="display:inline-block;border-radius:8px;overflow:hidden;' +
                    'box-shadow:0 3px 12px rgba(0,0,0,.18);border:1px solid #c00">' +
          '<div class="ccfnt-cal-month" style="background:#990000;color:#fff;font-size:1em;font-weight:700;' +
                      'letter-spacing:.12em;text-transform:uppercase;padding:7px 0 6px">' +
            moisFr[next.getMonth()] +
          '</div>' +
          '<div class="ccfnt-cal-day" style="background:#fff;color:#111;font-size:4.5em;font-weight:900;' +
                      'line-height:1;padding:10px 0 8px;font-family:Georgia,serif">' +
            next.getDate() +
          '</div>' +
        '</div>' +
        '<div style="margin-top:10px;color:#555;font-size:.82em;line-height:1.3">' +
          '<span class="ccfnt-jours-diff" style="display:block;font-size:2.6em;font-weight:800;line-height:1">' + diff + '</span>' +
          '<span>' + label + '</span>' +
        '</div>' +
      '</div>';
  }

  function go() {
    fetch('/api/masses', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (masses) {
        if (!Array.isArray(masses) || !masses.length) return;
        var dates = masses
          .filter(function (m) { return m && m.date; })
          .map(function (m) { var p = m.date.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); })
          .sort(function (a, b) { return a - b; });
        if (dates.length) render(dates);
      })
      .catch(function () { /* keep whatever static fallback is in the page */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', go);
  } else {
    go();
  }
})();
