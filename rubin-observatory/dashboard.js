// Mark the dashboard as JS-enhanced so CSS can hide pre-render notices.
(function () {
  document.documentElement.classList.add("docverse-js");
})();

// Humanize edition "updated" timestamps ("5 minutes ago", "yesterday").
//
// The template renders each <time class="updated"> with an ISO 8601 value in
// its datetime attribute and a plain date as fallback text. The full
// timestamp stays available on hover through the title attribute. Because
// the dashboard is rendered once at publish time, the relative text is
// computed here in the browser and refreshed every minute so it never goes
// stale in a long-lived tab.
(function () {
  if (typeof Intl === "undefined" || typeof Intl.RelativeTimeFormat !== "function") {
    return;
  }
  var formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  var units = [
    ["year", 365 * 24 * 60 * 60],
    ["month", 30 * 24 * 60 * 60],
    ["week", 7 * 24 * 60 * 60],
    ["day", 24 * 60 * 60],
    ["hour", 60 * 60],
    ["minute", 60],
  ];

  function humanize(date, now) {
    var seconds = Math.round((date.getTime() - now.getTime()) / 1000);
    if (Math.abs(seconds) < 60) {
      return "just now";
    }
    for (var i = 0; i < units.length; i++) {
      var unit = units[i][0];
      var size = units[i][1];
      if (Math.abs(seconds) >= size) {
        return formatter.format(Math.round(seconds / size), unit);
      }
    }
    return formatter.format(Math.round(seconds / 60), "minute");
  }

  function refresh() {
    var now = new Date();
    var nodes = document.querySelectorAll("time.updated[datetime]");
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var date = new Date(node.getAttribute("datetime"));
      if (isNaN(date.getTime())) {
        continue;
      }
      node.textContent = humanize(date, now);
    }
  }

  refresh();
  window.setInterval(refresh, 60 * 1000);
})();
