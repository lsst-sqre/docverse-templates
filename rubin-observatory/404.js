// Show the URL the reader asked for on the 404 page.
//
// The page is rendered once and served for every missing path, so the
// template cannot know the requested URL; it is read from the browser's
// location here. The paragraph stays hidden if this script does not run.
(function () {
  var p = document.querySelector(".error-page__url");
  if (!p) {
    return;
  }
  var code = p.querySelector("code");
  code.textContent = window.location.href;
  p.hidden = false;
})();
