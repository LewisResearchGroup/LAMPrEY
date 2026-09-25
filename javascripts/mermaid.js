document$.subscribe(function () {
  if (typeof mermaid === "undefined") {
    return;
  }

  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "loose",
  });

  document.querySelectorAll(".mermaid").forEach(function (block, index) {
    if (!block.id) {
      block.id = "mermaid-diagram-" + index;
    }
    block.removeAttribute("data-processed");
  });

  mermaid.run({
    querySelector: ".mermaid",
  });
});
