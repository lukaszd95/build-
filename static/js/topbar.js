(() => {
  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const framerMotion = window.framerMotion || window.FramerMotion;
  const lucideGlobal = window.lucideReact || window.LucideReact;

  if (!React || !ReactDOM) {
    console.error("React lub ReactDOM nie są dostępne. Topbar nie został wyrenderowany.");
    return;
  }

  const { useMemo, useState, useEffect, useRef } = React;
  const { motion, AnimatePresence } = framerMotion || {};
  const { Bell, ChevronDown, MessageSquare } = lucideGlobal || {};

  const h = React.createElement;

  const defaultProps = {
    appName: "AI Architekt",
    boards: ["Wybierz projekt"],
    currentBoard: "Wybierz projekt",
    lang: "PL",
    user: {
      name: "Jan Kowalski",
      email: "jan@example.com",
      avatarUrl: "https://i.pravatar.cc/64?img=12",
    },
    onCreateProject: () => {},
    onBoardChange: () => {},
    onChangeAvatar: () => {},
    onLogout: () => {},
    onOpenProfile: () => {},
    onOpenSettings: () => {},
    onOpenProjects: () => {},
    onOpenNotifications: null,
    onOpenComments: null,
  };

  const props = {
    ...defaultProps,
    ...(window.topbarProps || {}),
    user: {
      ...defaultProps.user,
      ...((window.topbarProps && window.topbarProps.user) || {}),
    },
  };

  const noop = () => {};

  function AppLogo() {
    return h(
      "div",
      {
        className:
          "relative h-8 w-8 rounded-xl overflow-hidden shadow-[0_8px_20px_rgba(0,0,0,0.12)] ring-1 ring-black/[0.06] bg-white",
      },
      h("img", {
        src: "/static/favicon.ico",
        alt: `${props.appName} logo`,
        className: "h-full w-full object-cover",
        draggable: false,
      })
    );
  }

  function PremiumGroup({ children }) {
    return h(
      "div",
      { className: "relative" },
      h("div", {
        className:
          "absolute -inset-1 rounded-[18px] blur-xl bg-[radial-gradient(60%_60%_at_50%_0%,rgba(0,0,0,0.18),transparent_70%)]",
      }),
      h(
        "div",
        {
          className:
            "relative rounded-[16px] p-[1px] bg-[linear-gradient(180deg,rgba(0,0,0,0.14),rgba(0,0,0,0.06))] shadow-[0_14px_44px_rgba(0,0,0,0.28)]",
        },
        h(
          "div",
          {
            className:
              "rounded-[15px] bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(245,247,250,0.82))] backdrop-blur-xl ring-1 ring-white/60 px-1.5 py-1 flex items-center gap-1",
          },
          children
        )
      )
    );
  }

  function DividerLine({ className = "" }) {
    return h("div", { className: `h-6 w-px bg-neutral-200 ${className}` });
  }

  function PillIcon({ children, label, onClick, buttonRef = null }) {
    return h(
      "button",
      {
        type: "button",
        "aria-label": label,
        title: label,
        onClick: (event) => {
          event.stopPropagation();
          (onClick || noop)(event);
        },
        ref: buttonRef,
        className:
          "h-8 w-8 rounded-xl inline-flex items-center justify-center text-neutral-900/80 hover:bg-white/70 transition",
      },
      children
    );
  }

  function Dropdown({ children, align = "left", narrow }) {
    const width = narrow ? "min-w-[220px]" : "min-w-[280px]";
    const baseClassName =
      `topbar-dropdown absolute mt-1 ${width} rounded-3xl overflow-hidden shadow-[0_24px_80px_rgba(0,0,0,0.26)] ring-1 ring-black/[0.08] ` +
      (align === "right" ? "right-0" : "left-0");

    const content = h(
      "div",
      { className: "relative" },
      h(
        "div",
        { className: "absolute -top-2 left-1/2 -translate-x-1/2" },
        h("div", { className: "h-2 w-10 rounded-full bg-black/10" })
      ),
      h(
        "div",
        { className: "p-[1px] bg-[linear-gradient(180deg,rgba(0,0,0,0.16),rgba(0,0,0,0.06))]" },
        h(
          "div",
          { className: "bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(244,246,249,0.92))]" },
          h("div", { className: "pt-2" }, children)
        )
      )
    );

    if (motion) {
      return h(
        motion.div,
        {
          initial: { opacity: 0, y: -10, scale: 0.985 },
          animate: { opacity: 1, y: 0, scale: 1 },
          exit: { opacity: 0, y: -10, scale: 0.985 },
          transition: { duration: 0.16 },
          className: baseClassName,
        },
        content
      );
    }

    return h("div", { className: baseClassName }, content);
  }

  function DropdownItem({ children, onClick, danger, active }) {
    return h(
      "button",
      {
        type: "button",
        onClick: (event) => {
          event.preventDefault();
          event.stopPropagation();
          (onClick || noop)();
        },
        className:
          "w-full text-left px-4 py-3 text-sm flex items-center gap-3 transition hover:bg-black/[0.03] " +
          (danger ? "text-red-600" : "text-neutral-900") +
          (active ? " font-semibold" : ""),
      },
      h("span", {
        className: `inline-block h-2 w-2 rounded-full ${active ? "bg-neutral-900" : "bg-black/10"}`,
      }),
      h("span", { className: "truncate" }, children)
    );
  }

  function Topbar() {
    const [open, setOpen] = useState(null);
    const [board, setBoard] = useState(props.currentBoard);
    const [viewMode, setViewMode] = useState("PZT");
    const [projectBoards, setProjectBoards] = useState(props.boards || []);
    const [alerts, setAlerts] = useState([]);
    const topbarContentRef = useRef(null);
    const bellButtonRef = useRef(null);
    const [alertsRightOffset, setAlertsRightOffset] = useState(0);

    useEffect(() => {
      setBoard(props.currentBoard);
    }, [props.currentBoard]);

    useEffect(() => {
      const handler = (event) => {
        const requestedMode = event?.detail?.mode;
        if (requestedMode === "3D" || requestedMode === "PZT") {
          setViewMode(requestedMode);
        }
      };

      window.addEventListener("view:mode:sync", handler);
      return () => window.removeEventListener("view:mode:sync", handler);
    }, []);

    useEffect(() => {
      const handler = (event) => {
        const detail = event.detail || {};
        const nextProjects = Array.isArray(detail.projects) ? detail.projects.filter(Boolean) : [];
        const nextCurrent = typeof detail.currentProject === "string" && detail.currentProject.trim()
          ? detail.currentProject.trim()
          : nextProjects[0] || "Wybierz projekt";
        if (nextProjects.length) {
          setProjectBoards(nextProjects);
        }
        setBoard(nextCurrent);
      };

      window.addEventListener("topbar:projects:update", handler);
      return () => window.removeEventListener("topbar:projects:update", handler);
    }, []);

    useEffect(() => {
      const handler = (event) => {
        const detail = event.detail || {};
        const message = detail.message;
        if (!message) return;
        const variant = detail.variant === "error" ? "error" : "success";
        const durationMs = Number.isFinite(detail.durationMs)
          ? Math.min(Math.max(detail.durationMs, 1200), 20000)
          : 4200;
        const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        setAlerts((prev) => [...prev, { id, message, variant }]);
        window.setTimeout(() => {
          setAlerts((prev) => prev.filter((item) => item.id !== id));
        }, durationMs);
      };
      window.addEventListener("topbar:notify", handler);
      window.topbarNotify = (message, variant) => {
        window.dispatchEvent(new CustomEvent("topbar:notify", { detail: { message, variant } }));
      };
      return () => {
        window.removeEventListener("topbar:notify", handler);
      };
    }, []);

    useEffect(() => {
      const updateAlertsOffset = () => {
        const contentElement = topbarContentRef.current;
        const bellElement = bellButtonRef.current;
        if (!contentElement || !bellElement) return;
        const contentRect = contentElement.getBoundingClientRect();
        const bellRect = bellElement.getBoundingClientRect();
        const offset = Math.max(0, contentRect.right - bellRect.right);
        setAlertsRightOffset(Math.round(offset));
      };

      updateAlertsOffset();
      window.addEventListener("resize", updateAlertsOffset);
      return () => {
        window.removeEventListener("resize", updateAlertsOffset);
      };
    }, [board, props.lang, props.user.avatarUrl]);

    const boards = useMemo(() => projectBoards, [projectBoards]);
    const closeAll = () => setOpen(null);

    const setMode = (mode) => {
      if (mode !== "PZT" && mode !== "3D") return;
      setViewMode(mode);
      window.dispatchEvent(new CustomEvent("topbar:view:change", { detail: { mode } }));
    };

    const onNotifications = props.onOpenNotifications || noop;
    const onComments = props.onOpenComments || noop;

    return h(
      "div",
      { className: "bg-transparent", onClick: closeAll },
      h(
        "div",
        { className: "sticky top-0 z-50" },
        h(
          "div",
          { className: "relative w-full px-0 pt-0" },
          alerts.length
            ? h(
                "div",
                {
                  className:
                    "topbar-alerts flex flex-col items-end gap-2",
                  style: { right: `${alertsRightOffset}px` },
                },
                alerts.map((alert) =>
                  h(
                    "div",
                    {
                      key: alert.id,
                      className: `topbar-alert topbar-alert-${alert.variant}`,
                      role: "status",
                      "aria-live": "polite",
                    },
                    alert.message
                  )
                )
              )
            : null,
          h(
            "div",
            { className: "flex items-center justify-between gap-3", ref: topbarContentRef },
            h(
              PremiumGroup,
              null,
              h(
                "div",
                { className: "flex items-center gap-2 pl-1 pr-1" },
                h(AppLogo, null),
                h("span", { className: "font-semibold tracking-tight" }, props.appName)
              ),
              h(DividerLine, { className: "mx-1" }),
              h(
                "button",
                {
                  type: "button",
                  title: "Dodaj nowy projekt",
                  "aria-label": "Dodaj nowy projekt",
                  className:
                    "h-8 w-8 rounded-xl inline-flex items-center justify-center text-neutral-900/80 hover:bg-white/70 transition shadow-[0_1px_0_rgba(0,0,0,0.04)]",
                  onClick: (event) => {
                    event.stopPropagation();
                    props.onCreateProject();
                  },
                },
                h("span", { className: "text-lg leading-none" }, "+")
              ),
              h(
                "div",
                { className: "relative", onClick: (event) => event.stopPropagation() },
                h(
                  "button",
                  {
                    className:
                      "h-8 flex items-center gap-2 rounded-xl px-2.5 text-sm font-semibold text-neutral-800/90 hover:bg-white/70 transition",
                    title: "Aktualny projekt",
                    onClick: () => setOpen(open === "board" ? null : "board"),
                    type: "button",
                  },
                  h("span", { className: "max-w-[240px] truncate" }, board),
                  ChevronDown
                    ? h(ChevronDown, { className: "h-4 w-4 opacity-60" })
                    : h("span", { className: "text-xs opacity-60" }, "▾")
                ),
                AnimatePresence
                  ? h(
                      AnimatePresence,
                      null,
                      open === "board"
                        ? h(
                            Dropdown,
                            { align: "left" },
                            boards.map((entry) =>
                              h(
                                DropdownItem,
                                {
                                  key: entry,
                                  active: entry === board,
                                  onClick: () => {
                                    setBoard(entry);
                                    props.onBoardChange(entry);
                                    setOpen(null);
                                  },
                                },
                                entry
                              )
                            )
                          )
                        : null
                    )
                  : open === "board"
                    ? h(
                        Dropdown,
                        { align: "left" },
                        boards.map((entry) =>
                          h(
                            DropdownItem,
                            {
                              key: entry,
                              active: entry === board,
                              onClick: () => {
                                setBoard(entry);
                                props.onBoardChange(entry);
                                setOpen(null);
                              },
                            },
                            entry
                          )
                        )
                      )
                    : null
              )
              ,
              h(DividerLine, { className: "mx-1" }),
              h(
                "div",
                {
                  className:
                    "h-8 rounded-xl p-1 inline-flex items-center gap-1 bg-white/70 ring-1 ring-black/[0.06] shadow-[0_1px_0_rgba(0,0,0,0.04)]",
                  role: "tablist",
                  "aria-label": "Tryb widoku modelu",
                },
                h(
                  "button",
                  {
                    id: "pztPill",
                    type: "button",
                    className:
                      "h-6 px-3 rounded-lg text-[11px] font-semibold transition " +
                      (viewMode === "PZT"
                        ? "bg-white text-neutral-900 shadow-[0_2px_8px_rgba(15,23,42,0.16)]"
                        : "text-neutral-700/90 hover:bg-white/70"),
                    "aria-pressed": viewMode === "PZT",
                    onClick: (event) => {
                      event.stopPropagation();
                      setMode("PZT");
                    },
                  },
                  "PZT"
                ),
                h(
                  "button",
                  {
                    id: "d3Pill",
                    type: "button",
                    className:
                      "h-6 px-3 rounded-lg text-[11px] font-semibold transition " +
                      (viewMode === "3D"
                        ? "bg-neutral-900 text-white shadow-[0_2px_8px_rgba(15,23,42,0.28)]"
                        : "text-neutral-700/90 hover:bg-white/70"),
                    "aria-pressed": viewMode === "3D",
                    onClick: (event) => {
                      event.stopPropagation();
                      setMode("3D");
                    },
                  },
                  "3D"
                )
              )
            ),
            h(
              PremiumGroup,
              null,
              h(
                PillIcon,
                {
                  label: "Powiadomienia",
                  onClick: () => onNotifications(),
                  buttonRef: bellButtonRef,
                },
                Bell
                  ? h(Bell, { className: "h-[18px] w-[18px]" })
                  : h("span", { className: "text-xs" }, "🔔")
              ),
              h(
                PillIcon,
                { label: "Komentarze", onClick: () => onComments() },
                MessageSquare
                  ? h(MessageSquare, { className: "h-[18px] w-[18px]" })
                  : h("span", { className: "text-xs" }, "💬")
              ),
              h(DividerLine, { className: "mx-1" }),
              h(
                "div",
                {
                  className:
                    "h-8 rounded-xl px-2 inline-flex items-center gap-2 text-[11px] font-semibold tracking-wide text-neutral-800/80 bg-white/70 ring-1 ring-black/[0.06] shadow-[0_1px_0_rgba(0,0,0,0.04)]",
                  title: "Język aplikacji",
                  "aria-label": "Język aplikacji",
                },
                h("span", null, props.lang),
                props.lang === "PL"
                  ? h(
                      "span",
                      {
                        className:
                          "h-4 w-5 rounded-sm overflow-hidden ring-1 ring-black/10 flex flex-col",
                      },
                      h("span", { className: "flex-1 bg-white" }),
                      h("span", { className: "flex-1 bg-red-600" })
                    )
                  : null,
                props.lang === "EN"
                  ? h(
                      "span",
                      {
                        className:
                          "h-4 w-5 rounded-sm overflow-hidden ring-1 ring-black/10 bg-blue-800 flex items-center justify-center text-white text-[9px] font-bold",
                      },
                      "UK"
                    )
                  : null,
                props.lang === "DE"
                  ? h(
                      "span",
                      {
                        className:
                          "h-4 w-5 rounded-sm overflow-hidden ring-1 ring-black/10 flex flex-col",
                      },
                      h("span", { className: "flex-1 bg-black" }),
                      h("span", { className: "flex-1 bg-red-600" }),
                      h("span", { className: "flex-1 bg-yellow-400" })
                    )
                  : null
              ),
              h(
                "div",
                { className: "relative", onClick: (event) => event.stopPropagation() },
                h(
                  PillIcon,
                  {
                    label: "Konto",
                    onClick: () => setOpen(open === "user" ? null : "user"),
                  },
                  h("img", {
                    src: props.user.avatarUrl,
                    alt: "Avatar użytkownika",
                    className: "h-6 w-6 rounded-full object-cover",
                    draggable: false,
                  })
                ),
                AnimatePresence
                  ? h(
                      AnimatePresence,
                      null,
                      open === "user"
                        ? h(
                            Dropdown,
                            { align: "right", narrow: true },
                            h(
                              "div",
                              { className: "px-3 py-2 flex items-center gap-3" },
                              h("img", {
                                src: props.user.avatarUrl,
                                alt: "Avatar użytkownika",
                                className: "h-10 w-10 rounded-full object-cover",
                                draggable: false,
                              }),
                              h(
                                "div",
                                null,
                                h("div", { className: "text-sm font-semibold" }, props.user.name),
                                h("div", { className: "text-xs text-neutral-500" }, props.user.email)
                              )
                            ),
                            h(
                              DropdownItem,
                              { onClick: () => props.onChangeAvatar() },
                              "Zmień avatar"
                            ),
                            h("div", { className: "h-px bg-neutral-100" }),
                            h(
                              DropdownItem,
                              { onClick: () => props.onOpenProfile() },
                              "Profil"
                            ),
                            h(
                              DropdownItem,
                              { onClick: () => props.onOpenSettings() },
                              "Ustawienia"
                            ),
                            h(
                              DropdownItem,
                              { onClick: () => (props.onOpenProjects || props.onCreateProject)() },
                              "Projekty"
                            ),
                            h("div", { className: "h-px bg-neutral-100 my-1" }),
                            h(
                              DropdownItem,
                              { danger: true, onClick: () => props.onLogout() },
                              "Wyloguj"
                            )
                          )
                        : null
                    )
                  : open === "user"
                    ? h(
                        Dropdown,
                        { align: "right", narrow: true },
                        h(
                          "div",
                          { className: "px-3 py-2 flex items-center gap-3" },
                          h("img", {
                            src: props.user.avatarUrl,
                            alt: "Avatar użytkownika",
                            className: "h-10 w-10 rounded-full object-cover",
                            draggable: false,
                          }),
                          h(
                            "div",
                            null,
                            h("div", { className: "text-sm font-semibold" }, props.user.name),
                            h("div", { className: "text-xs text-neutral-500" }, props.user.email)
                          )
                        ),
                        h(
                          DropdownItem,
                          { onClick: () => props.onChangeAvatar() },
                          "Zmień avatar"
                        ),
                        h("div", { className: "h-px bg-neutral-100" }),
                        h(
                          DropdownItem,
                          { onClick: () => props.onOpenProfile() },
                          "Profil"
                        ),
                        h(
                          DropdownItem,
                          { onClick: () => props.onOpenSettings() },
                          "Ustawienia"
                        ),
                        h(
                          DropdownItem,
                          { onClick: () => (props.onOpenProjects || props.onCreateProject)() },
                          "Projekty"
                        ),
                        h("div", { className: "h-px bg-neutral-100 my-1" }),
                        h(
                          DropdownItem,
                          { danger: true, onClick: () => props.onLogout() },
                          "Wyloguj"
                        )
                      )
                    : null
              )
            )
          )
        )
      )
    );
  }

  const rootEl = document.getElementById("topbar-root");
  if (!rootEl) {
    console.error("Brak elementu #topbar-root. Topbar nie został wyrenderowany.");
    return;
  }

  const root = ReactDOM.createRoot(rootEl);
  root.render(h(Topbar));
})();
