const overlay = document.querySelector("[data-loading-overlay]");
const loadingMessage = document.querySelector("[data-loading-message]");
let loadingTimeout = null;

function setLoading(isLoading, label = "Working...", submitter = null) {
  if (loadingTimeout) {
    window.clearTimeout(loadingTimeout);
    loadingTimeout = null;
  }

  if (!isLoading) {
    document.body.classList.remove("is-loading");
    if (overlay) {
      overlay.setAttribute("aria-hidden", "true");
    }
    if (loadingMessage) {
      loadingMessage.textContent = "Working...";
    }
    document.querySelectorAll("[data-loading-active='true']").forEach((button) => {
      if (button instanceof HTMLButtonElement) {
        if (button.dataset.originalHtml) {
          button.innerHTML = button.dataset.originalHtml;
        }
        if (button.dataset.wasDisabled === "false") {
          button.disabled = false;
        }
        delete button.dataset.originalHtml;
        delete button.dataset.wasDisabled;
        delete button.dataset.loadingActive;
      }
    });
    return;
  }

  document.body.classList.add("is-loading");
  if (overlay) {
    overlay.setAttribute("aria-hidden", "false");
  }
  if (loadingMessage) {
    loadingMessage.textContent = label;
  }
  if (submitter instanceof HTMLButtonElement) {
    submitter.dataset.originalHtml = submitter.innerHTML;
    submitter.dataset.wasDisabled = submitter.disabled ? "true" : "false";
    submitter.dataset.loadingActive = "true";
    submitter.textContent = submitter.dataset.loadingLabel || label;
    submitter.disabled = true;
  }

  loadingTimeout = window.setTimeout(() => {
    setLoading(false);
  }, 15000);
}

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!form.checkValidity()) {
      return;
    }

    const label = form.dataset.loadingLabel || "Working...";
    const submitter = event.submitter instanceof HTMLButtonElement ? event.submitter : null;
    setLoading(true, label, submitter);
  });
});

document.querySelectorAll("[data-spec-source-form]").forEach((form) => {
  const choices = form.querySelectorAll("[data-spec-source-choice]");
  const panels = form.querySelectorAll("[data-spec-source-panel]");

  function syncSpecSource() {
    const selected = form.querySelector("[data-spec-source-choice]:checked");
    const selectedSource = selected ? selected.value : "repository";

    panels.forEach((panel) => {
      const isActive = panel.dataset.specSourcePanel === selectedSource;
      panel.hidden = !isActive;
      panel.querySelectorAll("input, select").forEach((control) => {
        control.disabled = !isActive;
        if (control instanceof HTMLInputElement && control.type === "file") {
          control.required = isActive;
        }
        if (control instanceof HTMLSelectElement) {
          control.required = isActive;
        }
      });
    });
  }

  choices.forEach((choice) => {
    choice.addEventListener("change", syncSpecSource);
  });
  syncSpecSource();
});

document.querySelectorAll("[data-editor-form]").forEach((form) => {
  const editor = form.querySelector("[data-editor]");
  const originalSource = form.querySelector("[data-editor-original]");
  const position = form.querySelector("[data-editor-position]");
  const dirty = form.querySelector("[data-editor-dirty]");
  const diffSummary = form.querySelector("[data-editor-diff-summary]");
  const diffOutput = form.querySelector("[data-editor-diff]");
  const diffPanel = form.querySelector("[data-editor-diff-panel]");
  const original = originalSource ? originalSource.value : "";
  const history = [editor.value];
  let historyIndex = 0;
  let isApplyingHistory = false;

  if (!(editor instanceof HTMLTextAreaElement)) {
    return;
  }

  function escapeHtml(value) {
    return value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function pushHistory(value) {
    if (isApplyingHistory || history[historyIndex] === value) {
      return;
    }
    history.splice(historyIndex + 1);
    history.push(value);
    historyIndex = history.length - 1;
  }

  function setEditorValue(value, selectionStart = 0, selectionEnd = selectionStart) {
    editor.value = value;
    editor.focus();
    editor.setSelectionRange(selectionStart, selectionEnd);
    pushHistory(value);
    syncEditorState();
  }

  function updatePosition() {
    const beforeCursor = editor.value.slice(0, editor.selectionStart);
    const lines = beforeCursor.split("\n");
    const line = lines.length;
    const col = lines[lines.length - 1].length + 1;
    if (position) {
      position.textContent = `Line ${line}, Col ${col}`;
    }
  }

  function diffLines(before, after) {
    const beforeLines = before.split(/\r?\n/);
    const afterLines = after.split(/\r?\n/);
    if (beforeLines.join("\n") === afterLines.join("\n")) {
      return [];
    }
    if (beforeLines.length * afterLines.length > 250000) {
      return [{ type: "info", text: "Diff is large; save and review with your normal git diff tooling." }];
    }

    const table = Array.from({ length: beforeLines.length + 1 }, () =>
      Array(afterLines.length + 1).fill(0),
    );
    for (let i = beforeLines.length - 1; i >= 0; i -= 1) {
      for (let j = afterLines.length - 1; j >= 0; j -= 1) {
        table[i][j] =
          beforeLines[i] === afterLines[j]
            ? table[i + 1][j + 1] + 1
            : Math.max(table[i + 1][j], table[i][j + 1]);
      }
    }

    const rows = [];
    let i = 0;
    let j = 0;
    while (i < beforeLines.length && j < afterLines.length) {
      if (beforeLines[i] === afterLines[j]) {
        rows.push({ type: "context", text: beforeLines[i] });
        i += 1;
        j += 1;
      } else if (table[i + 1][j] >= table[i][j + 1]) {
        rows.push({ type: "remove", text: beforeLines[i] });
        i += 1;
      } else {
        rows.push({ type: "add", text: afterLines[j] });
        j += 1;
      }
    }
    while (i < beforeLines.length) {
      rows.push({ type: "remove", text: beforeLines[i] });
      i += 1;
    }
    while (j < afterLines.length) {
      rows.push({ type: "add", text: afterLines[j] });
      j += 1;
    }
    return rows;
  }

  function renderDiff() {
    const rows = diffLines(original, editor.value);
    if (!diffOutput || !diffSummary) {
      return;
    }
    if (!rows.length) {
      diffSummary.textContent = "No changes";
      diffOutput.textContent = "No changes.";
      return;
    }
    const added = rows.filter((row) => row.type === "add").length;
    const removed = rows.filter((row) => row.type === "remove").length;
    diffSummary.textContent = `+${added} / -${removed}`;
    diffOutput.innerHTML = rows
      .map((row) => {
        const marker = row.type === "add" ? "+" : row.type === "remove" ? "-" : " ";
        const className =
          row.type === "add"
            ? "diff-add"
            : row.type === "remove"
              ? "diff-remove"
              : row.type === "info"
                ? "diff-info"
                : "diff-context";
        return `<span class="${className}">${marker} ${escapeHtml(row.text)}</span>`;
      })
      .join("\n");
  }

  function syncEditorState() {
    updatePosition();
    if (dirty) {
      dirty.textContent = editor.value === original ? "Unchanged" : "Changed from generated";
    }
    renderDiff();
  }

  function selectedLineRange() {
    const start = editor.value.lastIndexOf("\n", editor.selectionStart - 1) + 1;
    let end = editor.value.indexOf("\n", editor.selectionEnd);
    if (end === -1) {
      end = editor.value.length;
    }
    return { start, end };
  }

  function indentSelection() {
    const { start, end } = selectedLineRange();
    const block = editor.value.slice(start, end);
    const replacement = block
      .split("\n")
      .map((line) => `  ${line}`)
      .join("\n");
    setEditorValue(
      editor.value.slice(0, start) + replacement + editor.value.slice(end),
      editor.selectionStart + 2,
      editor.selectionEnd + replacement.length - block.length,
    );
  }

  function outdentSelection() {
    const { start, end } = selectedLineRange();
    const block = editor.value.slice(start, end);
    const replacement = block
      .split("\n")
      .map((line) => line.replace(/^( {1,2}|\t)/, ""))
      .join("\n");
    setEditorValue(
      editor.value.slice(0, start) + replacement + editor.value.slice(end),
      Math.max(start, editor.selectionStart - 2),
      Math.max(start, editor.selectionEnd - (block.length - replacement.length)),
    );
  }

  function runCommand(command, button = null) {
    if (command === "undo" && historyIndex > 0) {
      isApplyingHistory = true;
      historyIndex -= 1;
      editor.value = history[historyIndex];
      isApplyingHistory = false;
      syncEditorState();
      editor.focus();
    } else if (command === "redo" && historyIndex < history.length - 1) {
      isApplyingHistory = true;
      historyIndex += 1;
      editor.value = history[historyIndex];
      isApplyingHistory = false;
      syncEditorState();
      editor.focus();
    } else if (command === "revert" && window.confirm("Revert this editor buffer to the generated version?")) {
      setEditorValue(original, 0, 0);
    } else if (command === "indent") {
      indentSelection();
    } else if (command === "outdent") {
      outdentSelection();
    } else if (command === "wrap") {
      editor.classList.toggle("is-wrapped");
      if (button) {
        button.setAttribute("aria-pressed", editor.classList.contains("is-wrapped") ? "true" : "false");
      }
    } else if (command === "toggle-diff" && diffPanel) {
      const isHidden = diffPanel.hidden;
      diffPanel.hidden = !isHidden;
      if (button) {
        button.setAttribute("aria-expanded", isHidden ? "true" : "false");
        const label = button.querySelector(".editor-command-label");
        if (label) {
          label.textContent = isHidden ? "Hide diff" : "Show diff";
        } else {
          button.lastChild.textContent = isHidden ? " Hide diff" : " Show diff";
        }
      }
    }
  }

  form.querySelectorAll("[data-editor-command]").forEach((button) => {
    button.addEventListener("click", () => runCommand(button.dataset.editorCommand, button));
  });

  editor.addEventListener("input", () => {
    pushHistory(editor.value);
    syncEditorState();
  });
  editor.addEventListener("keyup", updatePosition);
  editor.addEventListener("click", updatePosition);
  editor.addEventListener("keydown", (event) => {
    if (event.key === "Tab") {
      event.preventDefault();
      if (event.shiftKey) {
        outdentSelection();
      } else {
        indentSelection();
      }
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      form.requestSubmit();
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      runCommand(event.shiftKey ? "redo" : "undo");
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
      event.preventDefault();
      runCommand("redo");
    }
  });

  syncEditorState();
});

window.addEventListener("pageshow", () => {
  setLoading(false);
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    setLoading(false);
  }
});

if (window.lucide) {
  window.lucide.createIcons({
    attrs: {
      "aria-hidden": "true",
    },
  });
}
