(() => {
  const root = document.documentElement;
  const KEY = "oscar-theme";

  const stored = localStorage.getItem(KEY);
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  root.setAttribute("data-theme", stored || (prefersDark ? "dark" : "light"));

  const toggle = document.getElementById("themeToggle");
  toggle?.addEventListener("click", () => {
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem(KEY, next);
  });

  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());

  // Highlight current section in nav as the user scrolls.
  const links = Array.from(document.querySelectorAll(".nav-links a"));
  const sections = links
    .map(l => document.querySelector(l.getAttribute("href")))
    .filter(Boolean);

  if ("IntersectionObserver" in window && sections.length) {
    const map = new Map(sections.map((s, i) => [s, links[i]]));
    const io = new IntersectionObserver(entries => {
      entries.forEach(e => {
        const link = map.get(e.target);
        if (!link) return;
        if (e.isIntersecting) {
          links.forEach(l => l.style.color = "");
          link.style.color = "var(--text)";
        }
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    sections.forEach(s => io.observe(s));
  }
})();
