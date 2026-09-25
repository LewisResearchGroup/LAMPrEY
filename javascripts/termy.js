(function () {
  function buildTermy(container) {
    if (!container || container.dataset.termyInitialized === "true") {
      return;
    }

    const code = container.querySelector("pre code");
    if (!code) {
      return;
    }

    const text = code.textContent || "";
    const rawLines = text.replace(/\r\n/g, "\n").split("\n");
    const lines = rawLines.filter((line, idx, arr) => {
      if (line.trim() !== "") {
        return true;
      }
      const prev = idx > 0 ? arr[idx - 1].trim() : "";
      const next = idx < arr.length - 1 ? arr[idx + 1].trim() : "";
      return prev !== "" && next !== "";
    });

    const terminal = document.createElement("div");
    terminal.className = "termy-terminal";

    const header = document.createElement("div");
    header.className = "termy-terminal-header";
    for (let i = 0; i < 3; i += 1) {
      const dot = document.createElement("span");
      dot.className = "termy-terminal-dot";
      header.appendChild(dot);
    }

    const toolbar = document.createElement("div");
    toolbar.className = "termy-terminal-toolbar";

    const fastBtn = document.createElement("button");
    fastBtn.className = "termy-terminal-btn";
    fastBtn.type = "button";
    fastBtn.textContent = "Fast";

    const restartBtn = document.createElement("button");
    restartBtn.className = "termy-terminal-btn";
    restartBtn.type = "button";
    restartBtn.textContent = "Restart";

    toolbar.appendChild(fastBtn);
    toolbar.appendChild(restartBtn);
    header.appendChild(toolbar);

    const body = document.createElement("div");
    body.className = "termy-terminal-body";

    terminal.appendChild(header);
    terminal.appendChild(body);
    container.appendChild(terminal);
    container.classList.add("termy-ready");
    container.dataset.termyInitialized = "true";

    let lineIndex = 0;
    let fastMode = false;
    let timeoutId = null;
    let sessionId = 0;

    function schedule(fn, delay) {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(() => {
        timeoutId = null;
        fn();
      }, delay);
    }

    function clearPending() {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
        timeoutId = null;
      }
    }

    function typeLine(line, currentSession, options = {}) {
      if (currentSession !== sessionId) {
        return;
      }

      const row = document.createElement("div");
      row.className = options.rowClass || "termy-line";

      let content = null;
      let fullText = line;

      if (options.prompt === true) {
        const prompt = document.createElement("span");
        prompt.className = "termy-prompt";
        prompt.textContent = "$ ";
        row.appendChild(prompt);
        fullText = line.slice(2);
      }

      content = document.createElement("span");
      const cursor = document.createElement("span");
      cursor.className = "termy-cursor";
      cursor.textContent = "|";

      row.appendChild(content);
      row.appendChild(cursor);
      body.appendChild(row);

      let charIndex = 0;

      function tick() {
        if (currentSession !== sessionId) {
          return;
        }
        content.textContent = fullText.slice(0, charIndex);
        charIndex += 1;
        if (charIndex <= fullText.length) {
          schedule(tick, fastMode ? 0 : 35);
          return;
        }
        cursor.remove();
        lineIndex += 1;
        schedule(() => renderNext(currentSession), fastMode ? 0 : 240);
      }

      tick();
    }

    function renderNext(currentSession) {
      if (currentSession !== sessionId) {
        return;
      }
      if (lineIndex >= lines.length) {
        return;
      }

      const line = lines[lineIndex];
      if (line.startsWith("// ")) {
        typeLine(line, currentSession, {
          rowClass: "termy-line termy-comment",
        });
        return;
      }

      if (line.startsWith("$ ")) {
        typeLine(line, currentSession, {
          prompt: true,
        });
        return;
      }

      typeLine(line, currentSession, {
        rowClass: "termy-line termy-output",
      });
    }

    function renderAllRemaining(currentSession) {
      if (currentSession !== sessionId) {
        return;
      }
      while (lineIndex < lines.length) {
        const line = lines[lineIndex];
        if (line.startsWith("$ ")) {
          const row = document.createElement("div");
          row.className = "termy-line";

          const prompt = document.createElement("span");
          prompt.className = "termy-prompt";
          prompt.textContent = "$ ";

          const content = document.createElement("span");
          content.textContent = line.slice(2);

          row.appendChild(prompt);
          row.appendChild(content);
          body.appendChild(row);
        } else {
          const row = document.createElement("div");
          row.className = line.startsWith("// ")
            ? "termy-line termy-comment"
            : "termy-line termy-output";
          row.textContent = line;
          body.appendChild(row);
        }
        lineIndex += 1;
      }
    }

    function startAnimation(options = {}) {
      clearPending();
      body.textContent = "";
      lineIndex = 0;
      sessionId += 1;
      const currentSession = sessionId;
      if (options.fast === true) {
        fastMode = true;
        renderAllRemaining(currentSession);
        return;
      }
      renderNext(currentSession);
    }

    fastBtn.addEventListener("click", () => {
      fastMode = true;
      clearPending();
      sessionId += 1;
      renderAllRemaining(sessionId);
    });

    restartBtn.addEventListener("click", () => {
      fastMode = false;
      startAnimation();
    });

    startAnimation();
  }

  function initTermy() {
    document.querySelectorAll(".termy").forEach(buildTermy);
  }

  document.addEventListener("DOMContentLoaded", initTermy);
  if (typeof window.document$ !== "undefined" && window.document$ && window.document$.subscribe) {
    window.document$.subscribe(initTermy);
  }
})();
