export function normalizeIdentificationValue(value) {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

export function computeChangedIdentificationPayload(fields, draft, persisted) {
  const changed = {};
  for (const field of fields) {
    const nextRaw = draft?.[field];
    const prevRaw = persisted?.[field];
    const next = normalizeIdentificationValue(nextRaw) || null;
    const prev = normalizeIdentificationValue(prevRaw) || null;
    if (next !== prev) {
      changed[field] = next;
    }
  }
  return changed;
}

export function createIdentificationAutosave({
  fields,
  debounceMs = 500,
  persist,
  onStatus,
  onPersisted,
  retryDelayMs = 1500,
}) {
  const state = {
    persisted: Object.fromEntries(fields.map((field) => [field, null])),
    draft: Object.fromEntries(fields.map((field) => [field, ""])),
    timerId: null,
    inFlight: false,
    queued: false,
    lastErrorPayload: null,
  };

  function setStatus(status, message) {
    if (typeof onStatus === "function") onStatus(status, message);
  }

  async function flushNow() {
    const payload = computeChangedIdentificationPayload(fields, state.draft, state.persisted);
    if (!Object.keys(payload).length) {
      state.lastErrorPayload = null;
      setStatus("idle", "");
      return;
    }

    if (state.inFlight) {
      state.queued = true;
      return;
    }

    state.inFlight = true;
    setStatus("saving", "Zapisywanie…");

    try {
      const persisted = await persist(payload);
      fields.forEach((field) => {
        state.persisted[field] = normalizeIdentificationValue(persisted?.[field]) || null;
        state.draft[field] = normalizeIdentificationValue(persisted?.[field]);
      });
      state.lastErrorPayload = null;
      setStatus("saved", "Zapisano");
      if (typeof onPersisted === "function") onPersisted(persisted);
    } catch (error) {
      state.lastErrorPayload = payload;
      setStatus("error", "Błąd zapisu. Ponawiam…");
      globalThis.setTimeout(() => {
        scheduleFlush(0);
      }, retryDelayMs);
      throw error;
    } finally {
      state.inFlight = false;
      if (state.queued) {
        state.queued = false;
        scheduleFlush(0);
      }
    }
  }

  function scheduleFlush(waitMs = debounceMs) {
    globalThis.clearTimeout(state.timerId);
    state.timerId = globalThis.setTimeout(() => {
      flushNow().catch(() => {
        // status already updated; auto retry is scheduled.
      });
    }, waitMs);
  }

  return {
    setPersisted(data = {}) {
      fields.forEach((field) => {
        const normalized = normalizeIdentificationValue(data[field]);
        state.persisted[field] = normalized || null;
        state.draft[field] = normalized;
      });
      state.lastErrorPayload = null;
      setStatus("idle", "");
    },
    updateDraftField(field, value) {
      if (!fields.includes(field)) return;
      state.draft[field] = normalizeIdentificationValue(value);
      scheduleFlush();
    },
    flushOnBlur() {
      scheduleFlush(0);
    },
    retryNow() {
      if (!state.lastErrorPayload) return;
      scheduleFlush(0);
    },
    getState() {
      return {
        persisted: { ...state.persisted },
        draft: { ...state.draft },
        inFlight: state.inFlight,
        queued: state.queued,
      };
    },
  };
}
