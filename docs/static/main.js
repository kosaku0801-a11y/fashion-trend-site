(function () {
  "use strict";

  var headers = document.querySelectorAll(".section-head");
  if (!headers.length) {
    return;
  }

  if (!("IntersectionObserver" in window)) {
    headers.forEach(function (el) {
      el.classList.add("is-visible");
    });
    return;
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.2 }
  );

  headers.forEach(function (el) {
    observer.observe(el);
  });
})();
