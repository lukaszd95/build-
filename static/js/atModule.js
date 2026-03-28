const atModule = document.getElementById("atModule");

if (atModule) {
  const maxSizeMb = Number(atModule.dataset.atMaxSizeMb || 40);
  const maxFiles = Number(atModule.dataset.atMaxFiles || 20);
  const atDropzone = document.getElementById("atDropzone");
  const atFileInput = document.getElementById("atFileInput");
  const atChooseFilesBtn = document.getElementById("atChooseFilesBtn");
  const atClearQueueBtn = document.getElementById("atClearQueueBtn");
  const atStartProcessingBtn = document.getElementById("atStartProcessingBtn");
  const atFileList = document.getElementById("atFileList");
  const atEmptyState = document.getElementById("atEmptyState");
  const atValidationMessage = document.getElementById("atValidationMessage");
  const atStatusBoard = document.getElementById("atStatusBoard");

  const state = {
    queue: [],
    uploading: false,
  };

  const statusLabels = {
    READY: "gotowy do wysłania",
    UPLOADING: "wysyłanie",
    UPLOADED: "przesłano",
    ANALYZING: "analizowanie",
    ERROR: "błąd",
    COMPLETED: "ukończono",
  };

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let size = bytes;
    let idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size /= 1024;
      idx += 1;
    }
    return `${size.toFixed(size >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
  }

  function showMessage(message, variant = "error") {
    if (!message) {
      atValidationMessage.className = "mb-2 hidden rounded-lg border px-3 py-2 text-xs";
      atValidationMessage.textContent = "";
      return;
    }
    atValidationMessage.className = variant === "success"
      ? "mb-2 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-xs text-emerald-700"
      : "mb-2 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700";
    atValidationMessage.textContent = message;
  }

  function validateFile(file) {
    if (!file) return { ok: false, message: "Nie wybrano pliku." };
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      return { ok: false, message: `Plik ${file.name} nie jest PDF.` };
    }
    if (file.size <= 0) {
      return { ok: false, message: `Plik ${file.name} jest pusty.` };
    }
    if (file.size > maxSizeMb * 1024 * 1024) {
      return { ok: false, message: `Plik ${file.name} przekracza limit ${maxSizeMb} MB.` };
    }
    return { ok: true };
  }

  function isDuplicate(file) {
    return state.queue.some((item) => item.file.name === file.name && item.file.size === file.size);
  }

  function removeQueuedFile(localId) {
    state.queue = state.queue.filter((item) => item.localId !== localId);
    render();
  }

  function render() {
    atFileList.innerHTML = "";
    atEmptyState.classList.toggle("hidden", state.queue.length > 0);
    atStartProcessingBtn.disabled = state.queue.length === 0 || state.uploading;

    state.queue.forEach((item) => {
      const row = document.createElement("div");
      row.className = "at-file-row";
      const statusText = statusLabels[item.status] || item.status;
      row.innerHTML = `
        <div>
          <div class="flex items-center gap-2">
            <div class="truncate text-sm font-semibold text-zinc-900">${item.file.name}</div>
            <span class="at-status-badge">${statusText}</span>
          </div>
          <div class="at-file-meta">
            <span>Rozmiar: ${formatBytes(item.file.size)}</span>
            <span>Dodano: ${new Date(item.addedAt).toLocaleString("pl-PL")}</span>
            <span>Postęp: ${item.progress}%</span>
          </div>
          ${item.error ? `<div class="mt-1 text-xs text-rose-600">${item.error}</div>` : ""}
        </div>
        <div class="flex items-center gap-1">
          <button type="button" class="rounded-full border border-gray-300 bg-white px-3 py-1 text-xs font-semibold text-zinc-700 hover:bg-gray-50" data-action="details">Szczegóły</button>
          <button type="button" class="rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-100" data-action="retry">Ponów</button>
          <button type="button" class="rounded-full border border-rose-300 bg-rose-50 px-3 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100" data-action="remove">Usuń</button>
        </div>
      `;

      row.querySelector('[data-action="remove"]').addEventListener("click", () => removeQueuedFile(item.localId));
      row.querySelector('[data-action="details"]').addEventListener("click", () => {
        showMessage(`Dokument: ${item.file.name} | status: ${statusText}`, "success");
      });
      row.querySelector('[data-action="retry"]').addEventListener("click", async () => {
        if (!item.documentId) return;
        await retryProcessing(item);
      });

      atFileList.appendChild(row);
    });
  }

  function enqueueFiles(files) {
    const incoming = Array.from(files || []);
    if (!incoming.length) return;

    if (state.queue.length + incoming.length > maxFiles) {
      showMessage(`Limit plików został przekroczony. Maksymalnie ${maxFiles}.`);
      return;
    }

    const errors = [];
    for (const file of incoming) {
      const valid = validateFile(file);
      if (!valid.ok) {
        errors.push(valid.message);
        continue;
      }
      if (isDuplicate(file)) {
        errors.push(`Plik ${file.name} jest już na liście.`);
        continue;
      }
      state.queue.push({
        localId: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        file,
        status: "READY",
        progress: 0,
        addedAt: new Date().toISOString(),
        documentId: null,
        error: null,
      });
    }

    if (errors.length) {
      showMessage(errors.join(" "));
    } else {
      showMessage("Pliki dodane do kolejki.", "success");
    }
    render();
  }

  async function retryProcessing(item) {
    try {
      const response = await fetch(`/api/at/documents/${item.documentId}/retry`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Nie udało się ponowić przetwarzania.");
      item.status = payload.document.processingStatus || "COMPLETED";
      atStatusBoard.textContent = `Ponowiono analizę dla ${item.file.name}: ${statusLabels[item.status] || item.status}.`;
      render();
    } catch (error) {
      showMessage(error.message || "Błąd podczas ponawiania przetwarzania.");
    }
  }

  async function uploadAndProcessQueue() {
    if (!state.queue.length || state.uploading) return;
    state.uploading = true;
    atStatusBoard.textContent = "Wysyłanie dokumentów...";
    showMessage("");

    for (const item of state.queue) {
      if (item.documentId) continue;
      item.status = "UPLOADING";
      item.progress = 15;
      render();

      const formData = new FormData();
      formData.append("file", item.file);

      try {
        const response = await fetch("/api/at/documents", { method: "POST", body: formData });
        const payload = await response.json();
        if (!response.ok && response.status !== 207) {
          throw new Error(payload.error || payload.errors?.[0]?.error || "Nie udało się przesłać pliku.");
        }
        const uploaded = payload.documents?.[0];
        if (!uploaded) {
          throw new Error(payload.errors?.[0]?.error || "Upload zakończył się bez dokumentu.");
        }
        item.documentId = uploaded.id;
        item.progress = 70;
        item.status = "UPLOADED";

        const processResponse = await fetch(`/api/at/documents/${item.documentId}/process`, { method: "POST" });
        const processPayload = await processResponse.json();
        if (!processResponse.ok) {
          throw new Error(processPayload.error || "Nie udało się uruchomić przetwarzania.");
        }
        item.status = processPayload.document.processingStatus || "COMPLETED";
        item.progress = 100;
        atStatusBoard.textContent = `Przetworzono ${item.file.name}. Status: ${statusLabels[item.status] || item.status}.`;
      } catch (error) {
        item.status = "ERROR";
        item.error = error.message || "Błąd uploadu.";
        atStatusBoard.textContent = `Błąd dla ${item.file.name}.`;
      }
      render();
    }

    state.uploading = false;
    atStatusBoard.textContent = "Zakończono przetwarzanie kolejki AT.";
  }

  atChooseFilesBtn?.addEventListener("click", () => atFileInput?.click());
  atFileInput?.addEventListener("change", (event) => {
    enqueueFiles(event.target.files);
    atFileInput.value = "";
  });

  atClearQueueBtn?.addEventListener("click", () => {
    state.queue = [];
    showMessage("Lista plików została wyczyszczona.", "success");
    render();
  });

  atStartProcessingBtn?.addEventListener("click", uploadAndProcessQueue);

  atDropzone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    atDropzone.classList.add("is-dragover");
  });
  atDropzone?.addEventListener("dragleave", () => atDropzone.classList.remove("is-dragover"));
  atDropzone?.addEventListener("drop", (event) => {
    event.preventDefault();
    atDropzone.classList.remove("is-dragover");
    enqueueFiles(event.dataTransfer?.files);
  });
  atDropzone?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      atFileInput?.click();
    }
  });

  render();
}
