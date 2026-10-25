/* JEV // AI OS Primary Dashboard & Obsidian Live Graph (static/os.js)
 * Pure DOM, SVG & Canvas construction for strict CSP compliance.
 */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";

  var STATE = {
    frame: null,
    prevMetrics: {},
    prevCounts: {},
    pulsingNodes: {},
    pulseTarget: "gtm",
    pulseBannerActive: false,
    feed: [],
    board: null,
    plan: null,
    upcoming: [],
    calendarDir: "",
    icsCount: 0,
    docs: [],
    scratchFiles: [],
    selectedNode: "jev",
    streamConnected: false,
    framesReceived: 0,
    lastPing: "",
    obs: {
      mode: "ring",
      plugins: { flow: true, activity: true, strength: true },
      filter: "",
      selectedNote: "core.md",
      hoveredNote: null,
      rotX: 0.35,
      rotY: 0.0,
      panX: 0,
      panY: 0,
      dragging: false,
      dragStartX: 0,
      dragStartY: 0,
      moved: false,
      screenPositions: {},
      tick: 0
    }
  };

  // Left Vertical Sidebar coordinates (viewBox 0 0 310 780)
  var SIDEBAR_LANES = [
    { id: "aios",    title: "01 // AI OS (GOVERNANCE & TOOLS)", x: 10, y: 12,  w: 290, h: 222 },
    { id: "hermes",  title: "02 // HERMES RUNTIME",             x: 10, y: 248, w: 290, h: 126 },
    { id: "offline", title: "03 // OFFLINE PRODUCT & DIODES",   x: 10, y: 388, w: 290, h: 380 }
  ];

  var SIDEBAR_NODES = {
    brain:      { x: 22,  y: 42,  w: 128, h: 52 },
    mark:       { x: 160, y: 42,  w: 128, h: 52 },
    jev:        { x: 22,  y: 112, w: 266, h: 50 },
    hud:        { x: 22,  y: 174, w: 266, h: 48 },

    hermes:     { x: 22,  y: 278, w: 128, h: 82 },
    model:      { x: 160, y: 278, w: 128, h: 82 },

    inbox:      { x: 22,  y: 420, w: 266, h: 48 },
    harness:    { x: 22,  y: 486, w: 158, h: 54 },
    quarantine: { x: 190, y: 486, w: 98,  h: 54 },
    gtm:        { x: 22,  y: 558, w: 266, h: 52 },
    notify:     { x: 22,  y: 628, w: 158, h: 52 },
    relay:      { x: 190, y: 628, w: 98,  h: 52 }
  };

  // Expanded View 2 coordinates (viewBox 0 0 1120 620)
  var EXPANDED_LANES = [
    { id: "aios",    title: "01 // AI OS (GOVERNANCE & TOOLS)", x: 25,  y: 25, w: 270, h: 570 },
    { id: "hermes",  title: "02 // HERMES RUNTIME",             x: 355, y: 25, w: 300, h: 570 },
    { id: "offline", title: "03 // OFFLINE PRODUCT & DIODES",   x: 715, y: 25, w: 385, h: 570 }
  ];

  var EXPANDED_NODES = {
    brain:      { x: 50,  y: 70,  w: 220, h: 66 },
    mark:       { x: 50,  y: 175, w: 220, h: 66 },
    jev:        { x: 50,  y: 290, w: 220, h: 66 },
    hud:        { x: 50,  y: 415, w: 220, h: 66 },

    hermes:     { x: 390, y: 185, w: 230, h: 72 },
    model:      { x: 390, y: 345, w: 230, h: 72 },

    inbox:      { x: 740, y: 65,  w: 210, h: 64 },
    harness:    { x: 740, y: 175, w: 210, h: 68 },
    quarantine: { x: 965, y: 175, w: 125, h: 68 },
    gtm:        { x: 740, y: 300, w: 210, h: 68 },
    notify:     { x: 740, y: 420, w: 210, h: 64 },
    relay:      { x: 965, y: 420, w: 125, h: 64 }
  };

  function $(id) {
    return document.getElementById(id);
  }

  function clear(el) {
    if (!el) return;
    while (el.firstChild) {
      el.removeChild(el.firstChild);
    }
  }

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === undefined || v === null || v === false) return;
        if (k === "className") el.className = v;
        else if (k === "text") el.textContent = String(v);
        else if (k.indexOf("on") === 0 && typeof v === "function") {
          el.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (v === true) {
          el.setAttribute(k, "");
        } else {
          el.setAttribute(k, String(v));
        }
      });
    }
    if (Array.isArray(children)) {
      children.forEach(function (c) {
        if (c === null || c === undefined || c === false) return;
        el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
      });
    }
    return el;
  }

  function svgEl(tag, attrs, children) {
    var el = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === undefined || v === null || v === false) return;
        if (k === "className") el.setAttribute("class", String(v));
        else if (k === "text") el.textContent = String(v);
        else if (k.indexOf("on") === 0 && typeof v === "function") {
          el.addEventListener(k.slice(2).toLowerCase(), v);
        } else {
          el.setAttribute(k, String(v));
        }
      });
    }
    if (Array.isArray(children)) {
      children.forEach(function (c) {
        if (c) el.appendChild(c);
      });
    }
    return el;
  }

  function toast(msg) {
    var box = $("toasts");
    if (!box) return;
    var item = h("div", { className: "toast", text: msg });
    box.appendChild(item);
    setTimeout(function () {
      if (item.parentNode) item.parentNode.removeChild(item);
    }, 3200);
  }

  function api(url, opts) {
    var options = opts || {};
    var headers = options.headers || {};
    if (options.body && typeof options.body === "object") {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    options.headers = headers;
    options.cache = "no-store";
    return fetch(url, options).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          throw new Error(data.error || ("HTTP " + res.status));
        }
        return data;
      });
    });
  }

  // ==================== NAVIGATION, SIDEBAR & HIDDEN SECONDARY DRAWERS ====================
  function goToView(idx) {
    var container = $("views");
    if (!container) return;
    var views = container.querySelectorAll(".view");
    var target = views[idx];
    if (target) {
      container.scrollTo({ left: target.offsetLeft, behavior: "smooth" });
    }
    updateActiveTab(idx);
  }

  function updateActiveTab(idx) {
    var tabs = document.querySelectorAll("#view-tabs button");
    tabs.forEach(function (btn, i) {
      btn.classList.toggle("active", i === idx);
    });
    var dots = document.querySelectorAll("#dots .dot");
    dots.forEach(function (d, i) {
      d.classList.toggle("active", i === idx);
    });
  }

  function openDrawer(drawerName) {
    closeSheet();
    var scrim = $("drawer-scrim");
    var cal = $("drawer-calendar");
    var trk = $("drawer-tracker");
    var quar = $("drawer-quarantine");
    if (cal) cal.setAttribute("hidden", "");
    if (trk) trk.setAttribute("hidden", "");
    if (quar) quar.setAttribute("hidden", "");
    if (scrim) scrim.removeAttribute("hidden");
    if (drawerName === "calendar" && cal) {
      cal.removeAttribute("hidden");
    } else if (drawerName === "tracker" && trk) {
      trk.removeAttribute("hidden");
    } else if (drawerName === "quarantine" && quar) {
      quar.removeAttribute("hidden");
      loadQuarantineDrawer();
    }
  }

  function closeDrawers() {
    var scrim = $("drawer-scrim");
    var cal = $("drawer-calendar");
    var trk = $("drawer-tracker");
    var quar = $("drawer-quarantine");
    if (scrim) scrim.setAttribute("hidden", "");
    if (cal) cal.setAttribute("hidden", "");
    if (trk) trk.setAttribute("hidden", "");
    if (quar) quar.setAttribute("hidden", "");
  }

  function wireNavigation() {
    var sbToggle = $("sidebar-toggle");
    var sidebar = $("flow-sidebar");
    if (sbToggle && sidebar) {
      sbToggle.addEventListener("click", function () {
        sidebar.classList.toggle("collapsed");
      });
    }

    document.querySelectorAll("[data-go]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var idx = Number(btn.getAttribute("data-go") || "0");
        closeSheet();
        closeDrawers();
        goToView(idx);
      });
    });

    var container = $("views");
    if (container) {
      container.addEventListener("scroll", function () {
        var w = container.clientWidth || 1;
        var idx = Math.round(container.scrollLeft / w);
        updateActiveTab(idx);
      });
    }

    document.querySelectorAll("[data-drawer]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.getAttribute("data-drawer");
        var drawerEl = $("drawer-" + target);
        if (drawerEl && !drawerEl.hasAttribute("hidden")) {
          closeDrawers();
        } else {
          openDrawer(target);
        }
      });
    });

    document.querySelectorAll("[data-close-drawer]").forEach(function (btn) {
      btn.addEventListener("click", closeDrawers);
    });

    var dScrim = $("drawer-scrim");
    if (dScrim) dScrim.addEventListener("click", closeDrawers);

    document.querySelectorAll("[data-sheet]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeDrawers();
        openSheet(btn.getAttribute("data-sheet"));
      });
    });

    var closeBtn = $("sheet-close");
    if (closeBtn) closeBtn.addEventListener("click", closeSheet);
    var scrim = $("scrim");
    if (scrim) scrim.addEventListener("click", closeSheet);

    var pulseTrig = $("sidebar-pulse-trigger");
    if (pulseTrig) {
      pulseTrig.addEventListener("click", function () {
        triggerSidebarPulse("gtm", "+1", "GTM Outbox & Quarantine pulse active");
      });
    }

    var pulseAct = $("sidebar-pulse-action");
    if (pulseAct) {
      pulseAct.addEventListener("click", function () {
        selectFlowNode(STATE.pulseTarget || "gtm");
        if (STATE.pulseTarget === "gtm" || STATE.pulseTarget === "notify") {
          openSheet("outbox");
        } else if (STATE.pulseTarget === "inbox") {
          openSheet("inbox");
        }
      });
    }

    var pulseClose = $("sidebar-pulse-close");
    if (pulseClose) {
      pulseClose.addEventListener("click", function () {
        STATE.pulsingNodes = {};
        STATE.pulseBannerActive = false;
        updateSidebarPulseBanner();
        if (STATE.frame) {
          renderSvgFlowchart($("sidebar-flow-svg"), SIDEBAR_LANES, SIDEBAR_NODES, STATE.frame, true);
          renderSvgFlowchart($("flow-svg"), EXPANDED_LANES, EXPANDED_NODES, STATE.frame, false);
        }
      });
    }
  }

  function updateClock() {
    var el = $("clock");
    if (!el) return;
    var now = new Date();
    el.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  // ==================== BOARD, VITAL TASKS, TRACKER & SMART CALENDAR ====================
  function loadBoard() {
    return api("/api/os/board").then(function (data) {
      applyBoardPayload(data);
    }).catch(function (err) {
      toast("Board load error: " + err.message);
    });
  }

  function mutateBoard(op) {
    if (STATE.board) {
      op.revision = STATE.board.revision;
    }
    return api("/api/os/board", { method: "POST", body: op }).then(function (data) {
      applyBoardPayload(data);
      refreshTelemetryOnce();
    }).catch(function (err) {
      toast(err.message);
      loadBoard();
    });
  }

  function applyBoardPayload(data) {
    STATE.board = data.board || {};
    STATE.plan = data.plan || {};
    STATE.upcoming = data.upcoming || [];
    STATE.calendarDir = data.calendar_dir || "";
    STATE.icsCount = data.ics_events || 0;

    renderVitalTasks();
    renderKanban();
    renderGoals();
    renderCalendar();
  }

  function renderVitalTasks() {
    var list = $("vital-list");
    var countEl = $("vital-count");
    if (!list || !STATE.board) return;
    clear(list);

    var tasks = (STATE.board.tasks || []).filter(function (t) {
      return Boolean(t.vital);
    });
    var openCount = tasks.filter(function (t) { return t.status !== "done"; }).length;
    if (countEl) {
      countEl.textContent = openCount + " open / " + tasks.length + " vital";
      countEl.className = "tag " + (openCount ? "warn" : "ok");
    }

    if (!tasks.length) {
      list.appendChild(h("li", { className: "hint", text: "No vital tasks pinned. Open Tracker to add or star (★) a task." }));
      return;
    }

    tasks.forEach(function (t) {
      var isDone = t.status === "done";
      var row = h("li", { className: "vital-item" + (isDone ? " done" : "") }, [
        h("div", { className: "vital-left" }, [
          h("input", {
            type: "checkbox",
            checked: isDone,
            title: "Mark done",
            onChange: function () {
              mutateBoard({ op: "task.update", id: t.id, status: isDone ? "todo" : "done" });
            }
          }),
          h("span", { className: "vital-title", text: t.title })
        ]),
        h("div", { className: "task-actions" }, [
          h("span", { className: "tag", text: "P" + t.priority + " · " + t.estimate_min + "m" }),
          h("button", {
            className: "btn ghost sm",
            type: "button",
            title: "Unpin from vital",
            text: "★",
            onClick: function () {
              mutateBoard({ op: "task.update", id: t.id, vital: false });
            }
          })
        ])
      ]);
      list.appendChild(row);
    });
  }

  function renderKanban() {
    if (!STATE.board) return;
    var tasks = STATE.board.tasks || [];
    var countEl = $("task-count");
    var trigMeta = $("trig-trk-meta");
    var openTotal = tasks.filter(function (t) { return t.status !== "done"; }).length;
    if (countEl) countEl.textContent = openTotal + " active";
    if (trigMeta) trigMeta.textContent = openTotal + " open";

    var lanes = { todo: [], doing: [], done: [] };
    tasks.forEach(function (t) {
      var st = lanes[t.status] ? t.status : "todo";
      lanes[st].push(t);
    });

    ["todo", "doing", "done"].forEach(function (st) {
      var nEl = $("n-" + st);
      if (nEl) nEl.textContent = "(" + lanes[st].length + ")";
      var body = $("lane-" + st);
      if (!body) return;
      clear(body);

      lanes[st].forEach(function (t) {
        var nextStatus = st === "todo" ? "doing" : (st === "doing" ? "done" : "todo");
        var nextLabel = st === "todo" ? "Start ▸" : (st === "doing" ? "Done ✓" : "Reopen");
        var card = h("div", { className: "task-card" + (t.vital ? " vital" : "") }, [
          h("div", { className: "task-top" }, [
            h("span", { className: "task-title", text: t.title }),
            h("button", {
              className: "btn ghost sm",
              type: "button",
              title: "Toggle vital star",
              text: t.vital ? "★" : "☆",
              onClick: function () {
                mutateBoard({ op: "task.update", id: t.id, vital: !t.vital });
              }
            })
          ]),
          h("div", { className: "task-foot" }, [
            h("span", { text: "P" + t.priority + " · " + t.estimate_min + "m" + (t.due ? " · due " + t.due : "") }),
            h("div", { className: "task-actions" }, [
              h("button", {
                className: "btn sm",
                type: "button",
                text: nextLabel,
                onClick: function () {
                  mutateBoard({ op: "task.update", id: t.id, status: nextStatus });
                }
              }),
              h("button", {
                className: "btn ghost sm",
                type: "button",
                title: "Delete task",
                text: "✕",
                onClick: function () {
                  mutateBoard({ op: "task.delete", id: t.id });
                }
              })
            ])
          ])
        ]);
        body.appendChild(card);
      });
    });
  }

  function progressClass(pct) {
    if (pct >= 95) return "p100";
    if (pct >= 70) return "p75";
    if (pct >= 60) return "p67";
    if (pct >= 45) return "p50";
    if (pct >= 30) return "p33";
    if (pct >= 15) return "p25";
    return "p0";
  }

  function renderGoals() {
    var list = $("goal-list");
    var select = $("task-goal");
    if (!list || !STATE.board) return;
    clear(list);

    var goals = STATE.board.goals || [];
    if (select) {
      clear(select);
      select.appendChild(h("option", { value: "", text: "None" }));
      goals.forEach(function (g) {
        select.appendChild(h("option", { value: g.id, text: g.title }));
      });
    }

    if (!goals.length) {
      list.appendChild(h("p", { className: "hint", text: "No goals yet. Click '+ Goal' to add one." }));
      return;
    }

    goals.forEach(function (g) {
      var ms = g.milestones || [];
      var doneCount = ms.filter(function (m) { return Boolean(m.done); }).length;
      var pct = ms.length ? Math.round((doneCount * 100) / ms.length) : 0;

      var msUl = h("ul", { className: "ms-list" });
      ms.forEach(function (m) {
        msUl.appendChild(h("li", { className: "ms-row" + (m.done ? " done" : "") }, [
          h("label", { className: "vital-left" }, [
            h("input", {
              type: "checkbox",
              checked: Boolean(m.done),
              onChange: function () {
                mutateBoard({ op: "milestone.toggle", goal_id: g.id, id: m.id });
              }
            }),
            h("span", { text: m.title })
          ]),
          h("button", {
            className: "btn ghost sm",
            type: "button",
            text: "✕",
            onClick: function () {
              mutateBoard({ op: "milestone.delete", goal_id: g.id, id: m.id });
            }
          })
        ]));
      });

      var msInput = h("input", { placeholder: "Add milestone…", maxlength: "160", required: true });
      var msForm = h("form", {
        className: "add-row",
        onSubmit: function (ev) {
          ev.preventDefault();
          var val = msInput.value.trim();
          if (!val) return;
          mutateBoard({ op: "milestone.add", goal_id: g.id, title: val });
        }
      }, [
        msInput,
        h("button", { className: "btn sm", type: "submit", text: "+ Milestone" }),
        h("button", {
          className: "btn danger sm",
          type: "button",
          text: "Delete goal",
          onClick: function () {
            mutateBoard({ op: "goal.delete", id: g.id });
          }
        })
      ]);

      var details = h("details", { className: "goal-item" }, [
        h("summary", {}, [
          h("span", { text: g.title }),
          h("span", { className: "goal-head-right" }, [
            h("span", { className: "tag", text: g.horizon || "month" }),
            h("span", { className: "tag " + (pct === 100 && ms.length ? "ok" : "info"), text: doneCount + "/" + ms.length })
          ])
        ]),
        h("div", { className: "progress-bar" }, [
          h("div", { className: "progress-fill " + progressClass(pct) })
        ]),
        msUl,
        msForm
      ]);

      list.appendChild(details);
    });
  }

  function renderCalendar() {
    var plan = STATE.plan;
    if (!plan) return;

    var trigCal = $("trig-cal-meta");
    if (trigCal) {
      trigCal.textContent = (plan.blocks || []).length + " blocks · " + (plan.load_pct || 0) + "%";
    }

    var dayTag = $("plan-day");
    if (dayTag) {
      dayTag.textContent = (plan.is_today ? "TODAY · " : "NEXT WORKDAY · ") + (plan.date || "");
      dayTag.className = "tag " + (plan.is_today ? "info" : "warn");
    }

    var meta = $("plan-meta");
    if (meta) {
      clear(meta);
      var wd = plan.workday || {};
      meta.appendChild(h("span", { text: "Workday " + (wd.start || "09:00") + "–" + (wd.end || "18:00") }));
      meta.appendChild(h("span", { text: "Load " + (plan.load_pct || 0) + "% · Free " + (plan.free_min || 0) + "m" }));
    }

    var bar = $("daybar");
    if (bar) {
      clear(bar);
      var wdStart = (plan.workday && plan.workday.start_min) || 540;
      var wdEnd = (plan.workday && plan.workday.end_min) || 1080;
      var span = Math.max(1, wdEnd - wdStart);
      var timelineSvg = svgEl("svg", { viewBox: "0 0 1000 26", preserveAspectRatio: "none", width: "100%", height: "26" });

      (plan.blocks || []).forEach(function (b) {
        var x0 = Math.max(0, Math.min(1000, Math.round(((b.start_min - wdStart) * 1000) / span)));
        var x1 = Math.max(x0 + 6, Math.min(1000, Math.round(((b.end_min - wdStart) * 1000) / span)));
        var fill = b.vital ? "#f59e0b" : (b.kind === "task" ? "#06b6d4" : "#a855f7");
        timelineSvg.appendChild(svgEl("rect", {
          x: x0, y: 3, width: x1 - x0, height: 20, rx: 3, fill: fill
        }));
      });

      if (typeof plan.now_min === "number" && plan.now_min >= wdStart && plan.now_min <= wdEnd) {
        var nx = Math.round(((plan.now_min - wdStart) * 1000) / span);
        timelineSvg.appendChild(svgEl("line", {
          x1: nx, y1: 0, x2: nx, y2: 26, stroke: "#ef4444", "stroke-width": 3
        }));
      }
      bar.appendChild(timelineSvg);
    }

    var agenda = $("agenda");
    if (agenda) {
      clear(agenda);
      var blocks = plan.blocks || [];
      if (!blocks.length) {
        agenda.appendChild(h("li", { className: "hint", text: "No scheduled blocks in this window." }));
      }
      blocks.forEach(function (b) {
        var rowCls = "agenda-row " + (b.vital ? "vital" : b.kind);
        var kindBadge = b.kind === "task" ? (b.vital ? "AUTO · VITAL" : "AUTO · TASK") : "FIXED EVENT";
        var rightCtrl = b.kind === "event" ? h("button", {
          className: "btn ghost sm",
          type: "button",
          text: "✕",
          title: "Remove event",
          onClick: function () {
            mutateBoard({ op: "event.delete", id: b.id });
          }
        }) : (b.kind === "task" ? h("button", {
          className: "btn sm",
          type: "button",
          text: "Done ✓",
          onClick: function () {
            mutateBoard({ op: "task.update", id: b.id, status: "done" });
          }
        }) : null);

        agenda.appendChild(h("li", { className: rowCls }, [
          h("span", { className: "agenda-time", text: b.start + "–" + b.end }),
          h("span", { className: "agenda-title", text: b.title }),
          h("span", { className: "tag", text: kindBadge }),
          rightCtrl
        ]));
      });
    }

    var unsched = $("unscheduled");
    if (unsched) {
      clear(unsched);
      var unList = plan.unscheduled || [];
      unList.forEach(function (u) {
        unsched.appendChild(h("div", { className: "alert-row warn" }, [
          h("div", { className: "alert-head" }, [
            h("span", { text: "Unscheduled: " + u.title }),
            h("span", { className: "tag warn", text: u.estimate_min + "m" })
          ]),
          h("div", { className: "alert-detail", text: u.reason })
        ]));
      });
    }

    if (STATE.board && STATE.board.settings) {
      var s = STATE.board.settings;
      var sStart = $("set-start");
      var sEnd = $("set-end");
      var sBuf = $("set-buffer");
      if (sStart && !sStart.matches(":focus")) sStart.value = s.workday_start || "09:00";
      if (sEnd && !sEnd.matches(":focus")) sEnd.value = s.workday_end || "18:00";
      if (sBuf && !sBuf.matches(":focus")) sBuf.value = String(s.buffer_min !== undefined ? s.buffer_min : 5);
    }

    var evDate = $("event-date");
    if (evDate && !evDate.value) {
      evDate.value = plan.date || "";
    }

    var icsHint = $("ics-hint");
    if (icsHint) {
      icsHint.textContent = "Drop any .ics file into " + (STATE.calendarDir || "hud-interface/calendar/") + " (" + STATE.icsCount + " imported event(s)).";
    }

    var upEl = $("upcoming");
    if (upEl) {
      clear(upEl);
      if (!STATE.upcoming.length) {
        upEl.appendChild(h("li", { className: "hint", text: "No fixed events in the next 7 days." }));
      } else {
        STATE.upcoming.forEach(function (ev) {
          upEl.appendChild(h("li", { className: "agenda-row event" }, [
            h("span", { className: "agenda-time", text: ev.date + " " + (ev.start || "") }),
            h("span", { className: "agenda-title", text: ev.title }),
            h("span", { className: "tag", text: ev.source || "board" })
          ]));
        });
      }
    }
  }

  function wireBoardForms() {
    var taskForm = $("task-form");
    if (taskForm) {
      taskForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var titleEl = $("task-title");
        var prioEl = $("task-priority");
        var estEl = $("task-est");
        var vitalEl = $("task-vital");
        var dueEl = $("task-due");
        var goalEl = $("task-goal");

        var title = titleEl.value.trim();
        if (!title) return;
        mutateBoard({
          op: "task.add",
          title: title,
          priority: Number(prioEl.value || 2),
          estimate_min: Number(estEl.value || 30),
          vital: Boolean(vitalEl.checked),
          due: dueEl ? dueEl.value : "",
          goal_id: goalEl ? goalEl.value : ""
        }).then(function () {
          titleEl.value = "";
          vitalEl.checked = false;
          toast("Task added & auto-scheduled");
        });
      });
    }

    var eventForm = $("event-form");
    if (eventForm) {
      eventForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var tEl = $("event-title");
        var dEl = $("event-date");
        var sEl = $("event-start");
        var eEl = $("event-end");
        var title = tEl.value.trim();
        if (!title) return;
        mutateBoard({
          op: "event.add",
          title: title,
          date: dEl.value,
          start: sEl.value,
          end: eEl.value
        }).then(function () {
          tEl.value = "";
          toast("Event scheduled");
        });
      });
    }

    var settingsForm = $("settings-form");
    if (settingsForm) {
      settingsForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        mutateBoard({
          op: "settings.update",
          workday_start: $("set-start").value,
          workday_end: $("set-end").value,
          buffer_min: Number($("set-buffer").value || 5)
        }).then(function () {
          toast("Workday schedule updated");
        });
      });
    }

    var goalToggle = $("goal-add-toggle");
    var goalForm = $("goal-form");
    if (goalToggle && goalForm) {
      goalToggle.addEventListener("click", function () {
        var isHidden = goalForm.hasAttribute("hidden");
        if (isHidden) {
          goalForm.removeAttribute("hidden");
          goalToggle.setAttribute("aria-expanded", "true");
        } else {
          goalForm.setAttribute("hidden", "");
          goalToggle.setAttribute("aria-expanded", "false");
        }
      });

      goalForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var tEl = $("goal-title");
        var hEl = $("goal-horizon");
        var title = tEl.value.trim();
        if (!title) return;
        mutateBoard({
          op: "goal.add",
          title: title,
          horizon: hEl.value
        }).then(function () {
          tEl.value = "";
          goalForm.setAttribute("hidden", "");
        });
      });
    }
  }

  // ==================== TELEMETRY STREAM & FLOWCHARTS WITH FADING TRANSMISSION LINES ====================
  function connectTelemetryStream() {
    var pill = $("stream-pill");
    var text = $("stream-text");

    if (typeof EventSource === "function") {
      var es = new EventSource("/api/os/stream");
      es.addEventListener("telemetry", function (ev) {
        STATE.streamConnected = true;
        STATE.framesReceived += 1;
        if (pill) pill.className = "pill live";
        if (text) text.textContent = "LIVE STREAM";
        try {
          var frame = JSON.parse(ev.data);
          applyTelemetryFrame(frame);
        } catch (err) {
          // ignore malformed frame
        }
      });
      es.addEventListener("ping", function (ev) {
        STATE.streamConnected = true;
        if (pill) pill.className = "pill live";
        if (text) text.textContent = "LIVE STREAM";
        try {
          var p = JSON.parse(ev.data);
          STATE.lastPing = p.ts || "";
          renderStreamStats();
        } catch (err) {
          // ignore
        }
      });
      es.onerror = function () {
        STATE.streamConnected = false;
        if (pill) pill.className = "pill err";
        if (text) text.textContent = "RECONNECTING";
      };
    }

    refreshTelemetryOnce();
    setInterval(function () {
      if (!STATE.streamConnected) {
        refreshTelemetryOnce();
      }
    }, 6000);
  }

  function refreshTelemetryOnce() {
    return api("/api/os/telemetry").then(function (frame) {
      applyTelemetryFrame(frame);
    }).catch(function () {});
  }

  function applyTelemetryFrame(frame) {
    if (!frame || !frame.nodes) return;
    recordChanges(frame);
    STATE.frame = frame;

    var meta = $("frame-meta");
    if (meta) {
      meta.textContent = "hash " + (frame.hash || "—") + " · " + (frame.ts || "");
    }

    renderAlerts(frame.alerts || []);
    renderBadges(frame.counters || {});
    renderSvgFlowchart($("sidebar-flow-svg"), SIDEBAR_LANES, SIDEBAR_NODES, frame, true);
    renderSvgFlowchart($("flow-svg"), EXPANDED_LANES, EXPANDED_NODES, frame, false);
    renderNodeInspector(STATE.selectedNode);
    renderObsidianInspector();
    renderStreamStats();
  }

  function triggerSidebarPulse(nodeId, deltaText, bannerText) {
    var exp = Date.now() + 25000;
    STATE.pulsingNodes[nodeId] = { until: exp, delta: deltaText || "+1" };
    if (nodeId === "gtm" && STATE.frame && STATE.frame.nodes && STATE.frame.nodes.quarantine) {
      var qCount = Number(STATE.frame.nodes.quarantine.count || 0);
      if (qCount > 0) {
        STATE.pulsingNodes.quarantine = { until: exp, delta: String(qCount) };
      }
    }
    STATE.pulseTarget = nodeId;
    STATE.pulseBannerActive = true;
    updateSidebarPulseBanner(bannerText);
    if (STATE.frame) {
      renderSvgFlowchart($("sidebar-flow-svg"), SIDEBAR_LANES, SIDEBAR_NODES, STATE.frame, true);
      renderSvgFlowchart($("flow-svg"), EXPANDED_LANES, EXPANDED_NODES, STATE.frame, false);
    }
  }

  function updateSidebarPulseBanner(customText) {
    var bar = $("sidebar-pulse-bar");
    var txt = $("sidebar-pulse-text");
    var sb = $("flow-sidebar");
    if (!bar) return;

    if (!STATE.pulseBannerActive) {
      bar.setAttribute("hidden", "");
      if (sb) sb.classList.remove("pulse-active");
      return;
    }

    bar.removeAttribute("hidden");
    if (sb) sb.classList.add("pulse-active");
    if (txt && customText) {
      txt.textContent = customText;
    }
  }

  function recordChanges(frame) {
    var nodes = frame.nodes || {};
    var nowStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    var isFirstFrame = Object.keys(STATE.prevCounts).length === 0;

    Object.keys(nodes).forEach(function (id) {
      var n = nodes[id];
      var sig = n.status + " | " + n.metric;
      if (STATE.prevMetrics[id] && STATE.prevMetrics[id] !== sig) {
        STATE.feed.unshift(nowStr + " · " + n.label + " → " + sig);
      } else if (!STATE.prevMetrics[id]) {
        STATE.feed.unshift(nowStr + " · " + n.label + ": " + sig);
      }
      STATE.prevMetrics[id] = sig;

      if (typeof n.count === "number") {
        var prevC = STATE.prevCounts[id];
        if (typeof prevC === "number" && n.count > prevC) {
          var diff = n.count - prevC;
          triggerSidebarPulse(id, "+" + diff, "⚡ " + n.label + " +" + diff + " (" + n.metric + ")");
        }
        STATE.prevCounts[id] = n.count;
      }
    });

    if (isFirstFrame) {
      var gtmNode = nodes.gtm || {};
      var quarNode = nodes.quarantine || {};
      if ((gtmNode.count || 0) > 0 || (quarNode.count || 0) > 0) {
        STATE.pulseTarget = (gtmNode.count || 0) > 0 ? "gtm" : "quarantine";
        STATE.pulseBannerActive = true;
        updateSidebarPulseBanner(
          "Outbox: " + (gtmNode.count || 0) + " review · Quarantine: " + (quarNode.count || 0) + " row(s)"
        );
      }
    }

    STATE.feed = STATE.feed.slice(0, 25);

    var feedEl = $("change-feed");
    var countEl = $("feed-count");
    if (countEl) countEl.textContent = String(STATE.feed.length);
    if (feedEl) {
      clear(feedEl);
      STATE.feed.forEach(function (line) {
        feedEl.appendChild(h("li", { text: line }));
      });
    }
  }

  function renderBadges(counters) {
    setBadge("badge-inbox", counters.inbox || 0);
    setBadge("badge-outbox", (counters.outbox_review || 0) + (counters.notify_pending || 0));
    setBadge("badge-quarantine", counters.quarantine || 0);
    setBadge("badge-alerts", counters.alerts_urgent || 0);

    var qTrig = $("trig-quar-meta");
    if (qTrig) {
      qTrig.textContent = (counters.quarantine || 0) > 0 ? (counters.quarantine + " hold") : "clean";
      qTrig.className = "tag " + ((counters.quarantine || 0) > 0 ? "warn" : "ok");
    }
  }

  function setBadge(id, count) {
    var el = $(id);
    if (!el) return;
    if (count > 0) {
      el.textContent = String(count);
      el.removeAttribute("hidden");
    } else {
      el.setAttribute("hidden", "");
    }
  }

  function renderAlerts(alerts) {
    var list = $("alert-list");
    var countEl = $("alert-count");
    if (countEl) {
      countEl.textContent = alerts.length + " active";
      var hasCrit = alerts.some(function (a) { return a.severity === "crit"; });
      var hasWarn = alerts.some(function (a) { return a.severity === "warn"; });
      countEl.className = "tag " + (hasCrit ? "err" : (hasWarn ? "warn" : "ok"));
    }
    if (!list) return;
    clear(list);

    if (!alerts.length) {
      list.appendChild(h("li", { className: "hint", text: "All clear. Zero active alerts." }));
      return;
    }

    alerts.forEach(function (a) {
      list.appendChild(h("li", {
        className: "alert-row " + (a.severity || "info"),
        onClick: function () {
          handleAlertClick(a);
        }
      }, [
        h("div", { className: "alert-head" }, [
          h("span", { text: a.title }),
          h("span", { className: "tag " + (a.severity === "crit" ? "err" : a.severity), text: (a.severity || "info").toUpperCase() })
        ]),
        h("div", { className: "alert-detail", text: a.detail })
      ]));
    });
  }

  function handleAlertClick(alert) {
    var t = alert.target;
    if (t === "calendar") openDrawer("calendar");
    else if (t === "today") openDrawer("tracker");
    else if (t === "quarantine") openDrawer("quarantine");
    else if (t === "outbox") openSheet("outbox");
    else if (t === "inbox") openSheet("inbox");
    else if (t === "flow") goToView(1);
    else goToView(0);
  }

  function edgePath(fromBox, toBox) {
    var x1 = fromBox.x + fromBox.w / 2;
    var y1 = fromBox.y + fromBox.h / 2;
    var x2 = toBox.x + toBox.w / 2;
    var y2 = toBox.y + toBox.h / 2;

    if (Math.abs(x2 - x1) > Math.abs(y2 - y1)) {
      var sx = x2 > x1 ? fromBox.x + fromBox.w : fromBox.x;
      var tx = x2 > x1 ? toBox.x : toBox.x + toBox.w;
      var mx = Math.round((sx + tx) / 2);
      return {
        d: "M " + sx + " " + y1 + " C " + mx + " " + y1 + ", " + mx + " " + y2 + ", " + tx + " " + y2,
        lx: mx,
        ly: Math.round((y1 + y2) / 2) - 5
      };
    } else {
      var sy = y2 > y1 ? fromBox.y + fromBox.h : fromBox.y;
      var ty = y2 > y1 ? toBox.y : toBox.y + toBox.h;
      var my = Math.round((sy + ty) / 2);
      return {
        d: "M " + x1 + " " + sy + " C " + x1 + " " + my + ", " + x2 + " " + my + ", " + x2 + " " + ty,
        lx: Math.round((x1 + x2) / 2) + 8,
        ly: my
      };
    }
  }

  function renderSvgFlowchart(svg, lanes, layout, frame, isCompact) {
    if (!svg) return;
    clear(svg);

    // Fading transmission line gradients & arrowheads
    var defs = svgEl("defs", {}, [
      svgEl("linearGradient", { id: "edge-fade-grad", x1: "0%", y1: "0%", x2: "100%", y2: "100%" }, [
        svgEl("stop", { offset: "0%", "stop-color": "#06b6d4", "stop-opacity": "0.05" }),
        svgEl("stop", { offset: "55%", "stop-color": "#06b6d4", "stop-opacity": "0.55" }),
        svgEl("stop", { offset: "100%", "stop-color": "#38bdf8", "stop-opacity": "0.95" })
      ]),
      svgEl("linearGradient", { id: "edge-hot-grad", x1: "0%", y1: "0%", x2: "100%", y2: "100%" }, [
        svgEl("stop", { offset: "0%", "stop-color": "#10b981", "stop-opacity": "0.08" }),
        svgEl("stop", { offset: "50%", "stop-color": "#06b6d4", "stop-opacity": "0.75" }),
        svgEl("stop", { offset: "100%", "stop-color": "#f59e0b", "stop-opacity": "1.0" })
      ]),
      svgEl("marker", {
        id: "arrow", viewBox: "0 0 10 10", refX: "8", refY: "5",
        markerWidth: "5", markerHeight: "5", orient: "auto-start-reverse"
      }, [
        svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: "#38bdf8" })
      ])
    ]);
    svg.appendChild(defs);

    lanes.forEach(function (lane) {
      svg.appendChild(svgEl("rect", {
        className: "flow-lane", x: lane.x, y: lane.y, width: lane.w, height: lane.h
      }));
      svg.appendChild(svgEl("text", {
        className: "flow-lane-title", x: lane.x + 12, y: lane.y + 18, text: lane.title
      }));
    });

    // Fading transmission edges (base line + animated fading trail)
    (frame.edges || []).forEach(function (edge) {
      var b1 = layout[edge.from];
      var b2 = layout[edge.to];
      if (!b1 || !b2) return;
      var geom = edgePath(b1, b2);
      svg.appendChild(svgEl("path", {
        className: "flow-edge-base",
        d: geom.d
      }));
      svg.appendChild(svgEl("path", {
        className: "flow-edge-fade" + (edge.active ? " active" : ""),
        d: geom.d,
        "marker-end": "url(#arrow)"
      }));
      if (!isCompact && edge.label) {
        svg.appendChild(svgEl("text", {
          className: "flow-edge-label",
          x: geom.lx,
          y: geom.ly,
          "text-anchor": "middle",
          text: edge.label
        }));
      }
    });

    var nodes = frame.nodes || {};
    var nowMs = Date.now();
    Object.keys(layout).forEach(function (id) {
      var box = layout[id];
      var data = nodes[id] || { label: id, status: "idle", metric: "—", detail: "" };
      var isSelected = STATE.selectedNode === id;
      var pInfo = STATE.pulsingNodes[id];
      var isDeltaPulsing = Boolean(pInfo && pInfo.until > nowMs);
      var isWatchNode = (id === "gtm" || id === "quarantine" || id === "notify") && Number(data.count || 0) > 0 && STATE.pulseBannerActive;
      var isPulsing = isDeltaPulsing || Boolean(data.hot) || isWatchNode;
      var cls = "flow-node " + (data.status || "idle") + (isSelected ? " selected" : "") + (isPulsing ? " pulsing-alert" : "");
      var maxChars = isCompact ? Math.max(12, Math.floor((box.w - 20) / 5.8)) : 28;

      var children = [];
      if (isPulsing) {
        children.push(svgEl("rect", {
          className: "flow-node-pulse-ring" + (data.status === "info" ? " info" : ""),
          x: box.x - 3,
          y: box.y - 3,
          width: box.w + 6,
          height: box.h + 6
        }));
      }

      children.push(
        svgEl("rect", { x: box.x, y: box.y, width: box.w, height: box.h }),
        svgEl("circle", { className: "flow-node-dot", cx: box.x + 12, cy: box.y + 18 }),
        svgEl("text", { className: "flow-node-title", x: box.x + 22, y: box.y + 22, text: String(data.label).slice(0, maxChars) }),
        svgEl("text", { className: "flow-node-metric", x: box.x + 12, y: box.y + 39, text: String(data.metric || "").slice(0, maxChars + 2) })
      );

      var badgeText = isDeltaPulsing ? pInfo.delta : (Number(data.count || 0) > 0 ? String(data.count) : "");
      if (badgeText) {
        var bw = Math.max(20, badgeText.length * 6 + 10);
        var bx = box.x + box.w - bw - 5;
        var by = box.y + 5;
        children.push(
          svgEl("rect", {
            className: "flow-node-badge" + (data.status === "info" && !isDeltaPulsing ? " info" : ""),
            x: bx, y: by, width: bw, height: 14
          }),
          svgEl("text", {
            className: "flow-node-badge-txt",
            x: bx + bw / 2,
            y: by + 10,
            "text-anchor": "middle",
            text: badgeText
          })
        );
      }

      var g = svgEl("g", {
        className: cls,
        onClick: function () {
          selectFlowNode(id);
        }
      }, children);
      svg.appendChild(g);
    });
  }

  function selectFlowNode(nodeId) {
    STATE.selectedNode = nodeId;
    if (STATE.frame) {
      renderSvgFlowchart($("sidebar-flow-svg"), SIDEBAR_LANES, SIDEBAR_NODES, STATE.frame, true);
      renderSvgFlowchart($("flow-svg"), EXPANDED_LANES, EXPANDED_NODES, STATE.frame, false);
    }
    renderNodeInspector(nodeId);

    // Sync selection with the Obsidian Graph Widget!
    var obs = STATE.frame && STATE.frame.obsidian;
    if (obs && Array.isArray(obs.notes)) {
      var match = obs.notes.find(function (n) { return n.flow_node === nodeId; });
      if (match) {
        STATE.obs.selectedNote = match.id;
        renderObsidianInspector();
      }
    }
  }

  function renderNodeInspector(nodeId) {
    if (!STATE.frame || !STATE.frame.nodes) return;
    var n = STATE.frame.nodes[nodeId];
    if (!n) return;

    // Update Left Sidebar Footer
    var sbTitle = $("sb-node-title");
    var sbStatus = $("sb-node-status");
    var sbMetric = $("sb-node-metric");
    var sbDetail = $("sb-node-detail");
    var sbActions = $("sb-node-actions");
    if (sbTitle) sbTitle.textContent = n.label;
    if (sbStatus) {
      sbStatus.textContent = (n.status || "idle").toUpperCase();
      sbStatus.className = "tag " + (n.status || "idle");
    }
    if (sbMetric) sbMetric.textContent = n.metric || "—";
    if (sbDetail) sbDetail.textContent = n.detail || "";

    if (sbActions) {
      clear(sbActions);
      if (nodeId === "hermes") {
        sbActions.appendChild(h("button", {
          className: "btn go sm",
          type: "button",
          text: "⚡ Run Hermes Probe",
          onClick: function () { executeCalibratedCommand("probe-8080"); }
        }));
      } else if (nodeId === "harness" || nodeId === "offline") {
        sbActions.appendChild(h("button", {
          className: "btn ok sm",
          type: "button",
          text: "⚡ Cycle Ledger Job",
          onClick: function () { executeCalibratedCommand("cycle-ledger"); }
        }));
        sbActions.appendChild(h("button", {
          className: "btn sm",
          type: "button",
          text: "📄 Test Fixture",
          onClick: function () { executeCalibratedCommand("cheap-read"); }
        }));
      } else if (nodeId === "gtm" || nodeId === "notify") {
        sbActions.appendChild(h("button", {
          className: "btn go sm",
          type: "button",
          text: "⚡ Dispatch Alerts",
          onClick: function () { executeCalibratedCommand("dispatch-alerts"); }
        }));
        sbActions.appendChild(h("button", {
          className: "btn sm",
          type: "button",
          text: "📑 Outbox Sheet",
          onClick: function () { openSheet("outbox"); }
        }));
      } else if (nodeId === "jev") {
        sbActions.appendChild(h("button", {
          className: "btn go sm",
          type: "button",
          text: "⚡ Screen Bash",
          onClick: function () { executeCalibratedCommand("guardrail-test"); }
        }));
        sbActions.appendChild(h("button", {
          className: "btn sm",
          type: "button",
          text: "🚀 Run E2E",
          onClick: function () { executeCalibratedCommand("e2e-run"); }
        }));
      } else if (nodeId === "brain") {
        sbActions.appendChild(h("button", {
          className: "btn sm",
          type: "button",
          text: "↻ Rescan Vault",
          onClick: function () { executeCalibratedCommand("rescan-vault"); }
        }));
      } else if (nodeId === "quarantine") {
        sbActions.appendChild(h("button", {
          className: "btn warn sm",
          type: "button",
          text: "⚠️ Open Quarantine Drawer",
          onClick: function () { openDrawer("quarantine"); }
        }));
        sbActions.appendChild(h("button", {
          className: "btn go sm",
          type: "button",
          text: "⚡ Auto-Recover All Rows",
          onClick: function () { autoRecoverAllQuarantine(); }
        }));
      } else if (nodeId === "aios" || nodeId === "cockpit") {
        sbActions.appendChild(h("button", {
          className: "btn sm",
          type: "button",
          text: "↻ Probe Endpoints",
          onClick: function () { runEndpointProbe(); }
        }));
      }
    }

    // Update View 2 Inspector
    var box = $("node-detail");
    var tag = $("node-status");
    if (tag) {
      tag.textContent = (n.status || "idle").toUpperCase();
      tag.className = "tag " + (n.status || "idle");
    }
    if (!box) return;
    clear(box);
    box.appendChild(h("div", { className: "mono", text: n.label + " [" + nodeId + "]" }));
    box.appendChild(h("div", { text: "Metric: " + (n.metric || "—") }));
    box.appendChild(h("div", { className: "muted", text: n.detail || "" }));

    var v2Actions = h("div", { className: "node-actions-bar" });
    if (nodeId === "hermes") {
      v2Actions.appendChild(h("button", { className: "btn go sm", type: "button", text: "⚡ Run Hermes 8080 Probe", onClick: function () { executeCalibratedCommand("probe-8080"); } }));
    } else if (nodeId === "quarantine") {
      v2Actions.appendChild(h("button", { className: "btn warn sm", type: "button", text: "⚠️ Open Quarantine Drawer", onClick: function () { openDrawer("quarantine"); } }));
      v2Actions.appendChild(h("button", { className: "btn go sm", type: "button", text: "⚡ Auto-Recover All Rows", onClick: function () { autoRecoverAllQuarantine(); } }));
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "↺ Reset Baseline", onClick: function () { resetQuarantineFixture(); } }));
    } else if (nodeId === "harness" || nodeId === "offline") {
      v2Actions.appendChild(h("button", { className: "btn ok sm", type: "button", text: "⚡ Cycle SQLite Ledger", onClick: function () { executeCalibratedCommand("cycle-ledger"); } }));
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "📄 Cheap Read Fixture", onClick: function () { executeCalibratedCommand("cheap-read"); } }));
    } else if (nodeId === "gtm" || nodeId === "notify") {
      v2Actions.appendChild(h("button", { className: "btn go sm", type: "button", text: "⚡ Dispatch SMTP Alerts", onClick: function () { executeCalibratedCommand("dispatch-alerts"); } }));
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "Open Outbox Diode", onClick: function () { openSheet("outbox"); } }));
    } else if (nodeId === "inbox") {
      v2Actions.appendChild(h("button", { className: "btn go sm", type: "button", text: "Open Inbox Diode", onClick: function () { openSheet("inbox"); } }));
    } else if (nodeId === "jev") {
      v2Actions.appendChild(h("button", { className: "btn go sm", type: "button", text: "⚡ Screen Bash Guardrail", onClick: function () { executeCalibratedCommand("guardrail-test"); } }));
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "🚀 Run E2E Pipeline", onClick: function () { executeCalibratedCommand("e2e-run"); } }));
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "🧠 System-One Eval", onClick: function () { executeCalibratedCommand("decide-system1"); } }));
    } else if (nodeId === "brain") {
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "↻ Rescan Second Brain", onClick: function () { executeCalibratedCommand("rescan-vault"); } }));
      v2Actions.appendChild(h("button", { className: "btn sm", type: "button", text: "🔍 Scout Vault Notes", onClick: function () { executeCalibratedCommand("vault-scout"); } }));
    }
    box.appendChild(v2Actions);
  }

  // ==================== INTERACTIVE OBSIDIAN SECOND BRAIN GRAPH WIDGET ====================
  function groupColor(group) {
    if (group === "core") return "#f59e0b";
    if (group === "hermes") return "#a855f7";
    if (group === "offline") return "#10b981";
    if (group === "vault") return "#f43f5e";
    if (group === "disabled") return "#64748b";
    return "#06b6d4";
  }

  function computeObsidianNodePositions(notes, w, h) {
    var cx = w / 2 + STATE.obs.panX;
    var cy = h / 2 + STATE.obs.panY;
    var mode = STATE.obs.mode;
    var positions = {};

    var ring1 = notes.filter(function (n) { return n.ring === 1; });
    var ring2 = notes.filter(function (n) { return n.ring === 2; });

    notes.forEach(function (n, idx) {
      var x = cx;
      var y = cy;
      var z = 0;

      if (mode === "ring") {
        if (n.ring === 0) {
          x = cx;
          y = cy;
        } else if (n.ring === 1) {
          var i1 = ring1.indexOf(n);
          var a1 = (i1 / Math.max(1, ring1.length)) * Math.PI * 2 - Math.PI / 2;
          var r1 = Math.min(w, h) * 0.25;
          x = cx + Math.cos(a1) * r1;
          y = cy + Math.sin(a1) * r1;
        } else {
          var i2 = ring2.indexOf(n);
          var a2 = (i2 / Math.max(1, ring2.length)) * Math.PI * 2 - Math.PI / 4;
          var r2 = Math.min(w, h) * 0.42;
          x = cx + Math.cos(a2) * r2;
          y = cy + Math.sin(a2) * r2;
        }
      } else if (mode === "hierarchy") {
        var topPad = 48;
        var rowH = (h - 96) / 2;
        if (n.ring === 0) {
          x = cx;
          y = topPad;
        } else if (n.ring === 1) {
          var h1 = ring1.indexOf(n);
          var span1 = w - 90;
          x = 45 + (span1 * (h1 + 0.5)) / Math.max(1, ring1.length) + STATE.obs.panX;
          y = topPad + rowH + (h1 % 2 === 0 ? -14 : 14);
        } else {
          var h2 = ring2.indexOf(n);
          var span2 = w - 100;
          x = 50 + (span2 * (h2 + 0.5)) / Math.max(1, ring2.length) + STATE.obs.panX;
          y = topPad + rowH * 2;
        }
      } else {
        // 3D Orbit or 3D Sphere
        var rx = 0, ry = 0, rz = 0;
        if (mode === "orbit3d") {
          if (n.ring === 0) {
            rx = 0; ry = 0; rz = 0;
          } else {
            var list = n.ring === 1 ? ring1 : ring2;
            var posIdx = list.indexOf(n);
            var ang = (posIdx / Math.max(1, list.length)) * Math.PI * 2 + STATE.obs.rotY * (n.ring === 1 ? 1 : -0.7);
            var rad = Math.min(w, h) * (n.ring === 1 ? 0.26 : 0.43);
            rx = Math.cos(ang) * rad;
            rz = Math.sin(ang) * rad;
            ry = (n.ring === 1 ? -18 : 22) * Math.sin(ang * 2);
          }
        } else {
          // 3D Fibonacci Sphere
          var N = notes.length;
          var phi = Math.acos(1 - (2 * (idx + 0.5)) / N);
          var theta = Math.PI * (1 + Math.sqrt(5)) * idx + STATE.obs.rotY;
          var sRad = Math.min(w, h) * 0.37;
          rx = sRad * Math.sin(phi) * Math.cos(theta);
          ry = sRad * Math.cos(phi);
          rz = sRad * Math.sin(phi) * Math.sin(theta);
        }
        // Rotate around X axis
        var cosX = Math.cos(STATE.obs.rotX);
        var sinX = Math.sin(STATE.obs.rotX);
        var yRot = ry * cosX - rz * sinX;
        var zRot = ry * sinX + rz * cosX;
        var scale = 520 / (520 + zRot);
        x = cx + rx * scale;
        y = cy + yRot * scale;
        z = zRot;
      }

      positions[n.id] = { x: x, y: y, z: z, node: n };
    });

    return positions;
  }

  function drawObsidianCanvas() {
    var canvas = $("obsidian-canvas");
    if (canvas && STATE.frame && STATE.frame.obsidian) {
      var rect = canvas.parentNode.getBoundingClientRect();
      var w = Math.max(300, Math.floor(rect.width));
      var h = Math.max(260, Math.floor(rect.height));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      var ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, w, h);

      var obs = STATE.frame.obsidian;
      var notes = obs.notes || [];
      var links = obs.links || [];
      var filter = STATE.obs.filter.toLowerCase();

      if (STATE.obs.mode === "orbit3d" || STATE.obs.mode === "sphere3d") {
        if (!STATE.obs.dragging) {
          STATE.obs.rotY += 0.0045;
        }
      }
      STATE.obs.tick += 1;

      var pos = computeObsidianNodePositions(notes, w, h);
      STATE.obs.screenPositions = pos;

      var focusId = STATE.obs.hoveredNote || STATE.obs.selectedNote;
      var connectedSet = {};
      if (focusId) {
        connectedSet[focusId] = true;
        links.forEach(function (lk) {
          if (lk.source === focusId) connectedSet[lk.target] = true;
          if (lk.target === focusId) connectedSet[lk.source] = true;
        });
      }

      // Draw orbit guides in ring mode
      if (STATE.obs.mode === "ring") {
        [0.25, 0.42].forEach(function (ratio) {
          ctx.beginPath();
          ctx.arc(w / 2 + STATE.obs.panX, h / 2 + STATE.obs.panY, Math.min(w, h) * ratio, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(56, 189, 248, 0.08)";
          ctx.lineWidth = 1;
          ctx.stroke();
        });
      }

      // 1. Draw Links (with connection strength scaling & fading data flow particles)
      links.forEach(function (lk, lIdx) {
        var p1 = pos[lk.source];
        var p2 = pos[lk.target];
        if (!p1 || !p2) return;

        var isFocusedLink = focusId && (lk.source === focusId || lk.target === focusId);
        var strength = lk.strength_pct || 50;
        var baseAlpha = isFocusedLink ? 0.72 : (focusId ? 0.14 : (strength / 190));
        var lineWidth = STATE.obs.plugins.strength
          ? (isFocusedLink ? 1.2 + (strength / 38) : 0.6 + (strength / 55))
          : (isFocusedLink ? 2.0 : 1.1);

        // Fading gradient line between the two notes
        var grad = ctx.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
        var c1 = groupColor(p1.node.group);
        var c2 = groupColor(p2.node.group);
        grad.addColorStop(0, c1);
        grad.addColorStop(1, c2);

        ctx.save();
        ctx.globalAlpha = baseAlpha;
        ctx.strokeStyle = grad;
        ctx.lineWidth = lineWidth;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
        ctx.restore();

        // Plugin 1: Fading Data Flow Particles along active links
        if (STATE.obs.plugins.flow && lk.active && lk.flow_rate > 0) {
          var speed = 0.0035 * lk.flow_rate;
          var t = ((STATE.obs.tick * speed) + (lIdx * 0.17)) % 1;
          // Draw a 4-segment fading comet trail along the link
          for (var tail = 0; tail < 4; tail++) {
            var tt = t - tail * 0.032;
            if (tt < 0) tt += 1;
            var px = p1.x + (p2.x - p1.x) * tt;
            var py = p1.y + (p2.y - p1.y) * tt;
            var radius = (3.1 - tail * 0.6) * (isFocusedLink ? 1.25 : 1.0);
            ctx.save();
            ctx.globalAlpha = (0.9 - tail * 0.22) * (isFocusedLink ? 1.0 : 0.75);
            ctx.fillStyle = isFocusedLink ? "#f59e0b" : "#38bdf8";
            ctx.beginPath();
            ctx.arc(px, py, Math.max(0.8, radius), 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }

        // Plugin 3: Connection Strength Weight Pill on focused links
        if (STATE.obs.plugins.strength && isFocusedLink) {
          var mx = (p1.x + p2.x) / 2;
          var my = (p1.y + p2.y) / 2;
          ctx.save();
          ctx.fillStyle = "rgba(7, 10, 16, 0.88)";
          ctx.strokeStyle = "rgba(56, 189, 248, 0.55)";
          ctx.lineWidth = 1;
          ctx.fillRect(mx - 16, my - 8, 32, 15);
          ctx.strokeRect(mx - 16, my - 8, 32, 15);
          ctx.fillStyle = "#e2e8f0";
          ctx.font = "600 9.5px Consolas, monospace";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(strength + "%", mx, my);
          ctx.restore();
        }
      });

      // 2. Draw Notes (with Node Activity Halos & labels)
      notes.forEach(function (n) {
        var p = pos[n.id];
        if (!p) return;
        var matchesFilter = !filter || n.label.toLowerCase().indexOf(filter) !== -1 || n.group.indexOf(filter) !== -1;
        var isSelected = STATE.obs.selectedNote === n.id;
        var isHovered = STATE.obs.hoveredNote === n.id;
        var isNeighbor = connectedSet[n.id];
        var col = groupColor(n.group);
        var act = n.activity_pct || 50;
        var baseR = n.ring === 0 ? 13 : (n.ring === 1 ? 9.5 : 8);

        ctx.save();
        ctx.globalAlpha = !matchesFilter ? 0.15 : (focusId && !isNeighbor ? 0.32 : 1.0);

        // Plugin 2: Node Activity Pulsing Halo
        if (STATE.obs.plugins.activity && act > 25) {
          var pulse = 1 + 0.22 * Math.sin(STATE.obs.tick * 0.06 + act);
          var haloR = baseR + (act / 14) * pulse;
          var radGrad = ctx.createRadialGradient(p.x, p.y, baseR * 0.5, p.x, p.y, haloR);
          radGrad.addColorStop(0, col);
          radGrad.addColorStop(1, "rgba(6, 182, 212, 0)");
          ctx.fillStyle = radGrad;
          ctx.beginPath();
          ctx.arc(p.x, p.y, haloR, 0, Math.PI * 2);
          ctx.fill();
        }

        // Core Node Circle
        ctx.beginPath();
        ctx.arc(p.x, p.y, baseR, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.fill();
        ctx.lineWidth = (isSelected || isHovered) ? 2.8 : 1.4;
        ctx.strokeStyle = (isSelected || isHovered) ? "#ffffff" : "#0b101b";
        ctx.stroke();

        // Note Label
        ctx.font = (isSelected || n.ring === 0 ? "700 11px " : "600 10px ") + "Consolas, monospace";
        ctx.textAlign = "center";
        ctx.fillStyle = isSelected ? "#ffffff" : "#cbd5e1";
        ctx.fillText(n.label, p.x, p.y + baseR + 13);

        if (STATE.obs.plugins.activity && (isSelected || isHovered)) {
          ctx.font = "600 9px Consolas, monospace";
          ctx.fillStyle = "#f59e0b";
          ctx.fillText("act " + act + "%", p.x, p.y - baseR - 6);
        }

        ctx.restore();
      });
    }
    requestAnimationFrame(drawObsidianCanvas);
  }

  function renderObsidianInspector() {
    var obs = STATE.frame && STATE.frame.obsidian;
    if (!obs || !Array.isArray(obs.notes)) return;

    var statsTag = $("obs-stats-tag");
    if (statsTag) {
      statsTag.textContent = obs.notes.length + " notes · " + (obs.links || []).length + " links";
    }

    var note = obs.notes.find(function (n) { return n.id === STATE.obs.selectedNote; }) || obs.notes[0];
    if (!note) return;

    var titleEl = $("obs-sel-title");
    var actEl = $("obs-sel-activity");
    var ringEl = $("obs-sel-ring");
    var sumEl = $("obs-sel-summary");
    var editBtn = $("obs-edit-note");
    if (titleEl) titleEl.textContent = note.label;
    if (actEl) {
      actEl.textContent = "Activity " + note.activity_pct + "%";
      actEl.className = "tag " + (note.activity_pct >= 85 ? "ok" : "info");
    }
    if (ringEl) ringEl.textContent = "Ring " + note.ring + " · " + note.group;
    if (sumEl) sumEl.textContent = note.summary || "";
    if (editBtn) {
      if (note.editable && note.scratch_file) {
        editBtn.removeAttribute("hidden");
      } else {
        editBtn.setAttribute("hidden", "");
      }
    }

    // Find connected notes sorted by connection strength
    var chips = $("obs-connected-chips");
    if (chips) {
      clear(chips);
      var neighbors = [];
      (obs.links || []).forEach(function (lk) {
        if (lk.source === note.id) neighbors.push({ id: lk.target, strength: lk.strength_pct });
        else if (lk.target === note.id) neighbors.push({ id: lk.source, strength: lk.strength_pct });
      });
      neighbors.sort(function (a, b) { return b.strength - a.strength; });

      neighbors.forEach(function (nb) {
        var targetNote = obs.notes.find(function (x) { return x.id === nb.id; });
        var label = (targetNote ? targetNote.label : nb.id) + " (" + nb.strength + "%)";
        chips.appendChild(h("button", {
          className: "chip",
          type: "button",
          text: label,
          onClick: function () {
            STATE.obs.selectedNote = nb.id;
            renderObsidianInspector();
            if (targetNote && targetNote.flow_node) {
              STATE.selectedNode = targetNote.flow_node;
              renderNodeInspector(targetNote.flow_node);
            }
          }
        }));
      });
    }
  }

  function wireObsidianWidget() {
    document.querySelectorAll("[data-obs-mode]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        STATE.obs.mode = btn.getAttribute("data-obs-mode") || "ring";
        STATE.obs.panX = 0;
        STATE.obs.panY = 0;
        document.querySelectorAll("[data-obs-mode]").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
      });
    });

    document.querySelectorAll("[data-obs-plug]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.getAttribute("data-obs-plug");
        STATE.obs.plugins[k] = !STATE.obs.plugins[k];
        btn.classList.toggle("plug-on", STATE.obs.plugins[k]);
      });
    });

    var search = $("obs-search");
    if (search) {
      search.addEventListener("input", function () {
        STATE.obs.filter = search.value.trim();
      });
    }

    var openDocBtn = $("obs-open-doc");
    if (openDocBtn) {
      openDocBtn.addEventListener("click", function () {
        var obs = STATE.frame && STATE.frame.obsidian;
        if (!obs) return;
        var note = obs.notes.find(function (n) { return n.id === STATE.obs.selectedNote; });
        if (note && note.doc_id) {
          openSheet("docs", note.doc_id);
        }
      });
    }

    var editNoteBtn = $("obs-edit-note");
    if (editNoteBtn) {
      editNoteBtn.addEventListener("click", function () {
        var obs = STATE.frame && STATE.frame.obsidian;
        if (!obs) return;
        var note = obs.notes.find(function (n) { return n.id === STATE.obs.selectedNote; });
        if (note && note.scratch_file) {
          openSheet("editor", note.scratch_file);
        }
      });
    }

    var rescanBtn = $("obs-rescan-btn");
    if (rescanBtn) {
      rescanBtn.addEventListener("click", function () {
        rescanBtn.disabled = true;
        api("/api/os/obsidian/rescan", { method: "POST", body: {} }).then(function (obs) {
          if (STATE.frame) STATE.frame.obsidian = obs;
          renderObsidianInspector();
          loadDocsAndScratch();
          toast("Rescanned markdown folders: " + (obs.notes || []).length + " notes · " + (obs.links || []).length + " links");
        }).catch(function (err) {
          toast("Rescan error: " + err.message);
        }).finally(function () {
          rescanBtn.disabled = false;
        });
      });
    }

    var addToggle = $("obs-add-toggle");
    var noteForm = $("obs-note-form");
    if (addToggle && noteForm) {
      addToggle.addEventListener("click", function () {
        var isHidden = noteForm.hasAttribute("hidden");
        if (isHidden) {
          noteForm.removeAttribute("hidden");
          addToggle.setAttribute("aria-expanded", "true");
          var tIn = $("obs-note-title");
          if (tIn) tIn.focus();
        } else {
          noteForm.setAttribute("hidden", "");
          addToggle.setAttribute("aria-expanded", "false");
        }
      });

      noteForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var titleIn = $("obs-note-title");
        var linksIn = $("obs-note-links");
        var flowIn = $("obs-note-flow");
        var sumIn = $("obs-note-summary");
        var title = titleIn ? titleIn.value.trim() : "";
        if (!title) return;
        api("/api/os/obsidian/note", {
          method: "POST",
          body: {
            title: title,
            links: linksIn ? linksIn.value : "core.md, verification",
            flow_node: flowIn ? flowIn.value : "brain",
            summary: sumIn ? sumIn.value.trim() : ""
          }
        }).then(function (res) {
          if (STATE.frame && res.obsidian) {
            STATE.frame.obsidian = res.obsidian;
          }
          if (res.note_id) {
            STATE.obs.selectedNote = res.note_id;
          }
          renderObsidianInspector();
          loadDocsAndScratch();
          if (titleIn) titleIn.value = "";
          if (sumIn) sumIn.value = "";
          noteForm.setAttribute("hidden", "");
          addToggle.setAttribute("aria-expanded", "false");
          toast("Created local scratch note: " + (res.saved && res.saved.name ? res.saved.name : title));
        }).catch(function (err) {
          toast("Note creation error: " + err.message);
        });
      });
    }

    var canvas = $("obsidian-canvas");
    if (canvas) {
      canvas.addEventListener("mousedown", function (ev) {
        STATE.obs.dragging = true;
        STATE.obs.moved = false;
        STATE.obs.dragStartX = ev.clientX;
        STATE.obs.dragStartY = ev.clientY;
      });

      window.addEventListener("mouseup", function () {
        STATE.obs.dragging = false;
      });

      canvas.addEventListener("mousemove", function (ev) {
        var rect = canvas.getBoundingClientRect();
        var mx = ev.clientX - rect.left;
        var my = ev.clientY - rect.top;

        if (STATE.obs.dragging) {
          var dx = ev.clientX - STATE.obs.dragStartX;
          var dy = ev.clientY - STATE.obs.dragStartY;
          if (Math.abs(dx) > 3 || Math.abs(dy) > 3) STATE.obs.moved = true;
          STATE.obs.dragStartX = ev.clientX;
          STATE.obs.dragStartY = ev.clientY;
          if (STATE.obs.mode === "orbit3d" || STATE.obs.mode === "sphere3d") {
            STATE.obs.rotY += dx * 0.008;
            STATE.obs.rotX = Math.max(-1.2, Math.min(1.2, STATE.obs.rotX + dy * 0.008));
          } else {
            STATE.obs.panX += dx;
            STATE.obs.panY += dy;
          }
          return;
        }

        // Hit-test hovered note
        var hit = null;
        var pos = STATE.obs.screenPositions || {};
        Object.keys(pos).forEach(function (id) {
          var p = pos[id];
          var dist = Math.hypot(mx - p.x, my - p.y);
          if (dist < 18) hit = id;
        });
        STATE.obs.hoveredNote = hit;
      });

      canvas.addEventListener("mouseleave", function () {
        STATE.obs.hoveredNote = null;
      });

      canvas.addEventListener("click", function (ev) {
        if (STATE.obs.moved) return;
        var rect = canvas.getBoundingClientRect();
        var mx = ev.clientX - rect.left;
        var my = ev.clientY - rect.top;
        var pos = STATE.obs.screenPositions || {};
        var clicked = null;
        Object.keys(pos).forEach(function (id) {
          var p = pos[id];
          if (Math.hypot(mx - p.x, my - p.y) < 20) clicked = p.node;
        });
        if (clicked) {
          STATE.obs.selectedNote = clicked.id;
          renderObsidianInspector();
          if (clicked.flow_node) {
            selectFlowNode(clicked.flow_node);
          }
        }
      });
    }

    requestAnimationFrame(drawObsidianCanvas);
  }

  function renderStreamStats() {
    var dl = $("stream-stats");
    var tag = $("stream-tag");
    if (tag) {
      tag.textContent = STATE.streamConnected ? "SSE CONNECTED" : "POLL FALLBACK";
      tag.className = "tag " + (STATE.streamConnected ? "ok" : "warn");
    }
    if (!dl || !STATE.frame) return;
    clear(dl);
    var pairs = [
      ["Transport", STATE.streamConnected ? "Server-Sent Events (/api/os/stream)" : "HTTP Poll (/api/os/telemetry)"],
      ["Frames received", String(STATE.framesReceived)],
      ["Frame hash", STATE.frame.hash || "—"],
      ["Frame timestamp", STATE.frame.ts || "—"],
      ["Board revision", String(STATE.frame.board_revision || 0)]
    ];
    pairs.forEach(function (kv) {
      dl.appendChild(h("dt", { text: kv[0] }));
      dl.appendChild(h("dd", { text: kv[1] }));
    });
  }

  // ==================== DOCS & EDITOR SHORTCUTS ====================
  function loadDocsAndScratch() {
    api("/api/os/docs").then(function (res) {
      STATE.docs = res.docs || [];
      var box = $("doc-links");
      if (!box) return;
      clear(box);
      STATE.docs.forEach(function (d) {
        if (!d.available) return;
        box.appendChild(h("button", {
          className: "chip",
          type: "button",
          text: d.group + ": " + d.title,
          onClick: function () {
            openSheet("docs", d.id);
          }
        }));
      });
    }).catch(function () {});

    api("/api/os/editor/files").then(function (res) {
      STATE.scratchFiles = res.files || [];
      var box = $("recent-files");
      if (!box) return;
      clear(box);
      if (!STATE.scratchFiles.length) {
        box.appendChild(h("span", { className: "hint", text: "No scratch files yet — open Editor to create one." }));
        return;
      }
      STATE.scratchFiles.slice(0, 6).forEach(function (f) {
        box.appendChild(h("button", {
          className: "chip",
          type: "button",
          text: f.name,
          onClick: function () {
            openSheet("editor", f.name);
          }
        }));
      });
    }).catch(function () {});
  }

  // ==================== VIEW 3: SYSTEMS ACTIONS ====================
  function wireSystemsView() {
    var e2eBtn = $("run-e2e");
    if (e2eBtn) {
      e2eBtn.addEventListener("click", function () {
        var tag = $("e2e-tag");
        if (tag) { tag.textContent = "running…"; tag.className = "tag warn"; }
        e2eBtn.disabled = true;
        api("/api/jev-e2e", { method: "POST", body: { stage_to_outbox: true } }).then(function (res) {
          if (tag) { tag.textContent = res.outcome || "done"; tag.className = "tag ok"; }
          renderE2EStages(res.stages || []);
          refreshTelemetryOnce();
          loadSystemLogs();
          runEndpointProbe();
          toast("E2E pipeline finished (" + (res.outcome || "done") + ")");
        }).catch(function (err) {
          if (tag) { tag.textContent = "error"; tag.className = "tag err"; }
          toast("E2E error: " + err.message);
        }).finally(function () {
          e2eBtn.disabled = false;
        });
      });
    }

    // --- Wire Calibrated Command Console ---
    document.querySelectorAll("[data-cmd]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        executeCalibratedCommand(btn.dataset.cmd);
      });
    });

    var guardCmdBtn = $("btn-run-guardrail-cmd");
    var guardCmdInput = $("guardrail-cmd-input");
    if (guardCmdBtn && guardCmdInput) {
      guardCmdBtn.addEventListener("click", function () {
        executeCalibratedCommand("guardrail-test", guardCmdInput.value.trim());
      });
      guardCmdInput.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          executeCalibratedCommand("guardrail-test", guardCmdInput.value.trim());
        }
      });
    }

    document.querySelectorAll("[data-preset]").forEach(function (pBtn) {
      pBtn.addEventListener("click", function () {
        if (guardCmdInput) guardCmdInput.value = pBtn.dataset.preset;
        executeCalibratedCommand("guardrail-test", pBtn.dataset.preset);
      });
    });

    var clearConsoleBtn = $("clear-cmd-console");
    if (clearConsoleBtn) {
      clearConsoleBtn.addEventListener("click", function () {
        var out = $("cmd-console-output");
        if (out) out.textContent = "Console output cleared. Ready for next command.";
      });
    }

    var epProbeBtn = $("run-endpoint-probe");
    if (epProbeBtn) {
      epProbeBtn.addEventListener("click", function () {
        runEndpointProbe();
      });
    }

    var logsRefreshBtn = $("refresh-data-logs");
    if (logsRefreshBtn) {
      logsRefreshBtn.addEventListener("click", function () {
        loadLiveDataLogs();
      });
    }

    var probeBtn = $("run-probe");
    if (probeBtn) {
      probeBtn.addEventListener("click", function () {
        executeCalibratedCommand("probe-8080");
      });
    }

    loadSystemLogs();
    runEndpointProbe();
  }

  function executeCalibratedCommand(cmd, customInput) {
    var out = $("cmd-console-output");
    var badge = $("cmd-privilege-badge");
    if (badge) { badge.textContent = "Executing " + cmd + "…"; badge.className = "tag warn"; }

    function logOut(title, data, isErr) {
      if (badge) { badge.textContent = "Operator Level 10 Active"; badge.className = "tag ok"; }
      var text = typeof data === "object" ? JSON.stringify(data, null, 2) : String(data);
      var line = "[" + new Date().toISOString() + "] COMMAND EXECUTION: " + title + "\n" + text;
      if (out) out.textContent = line;
      var probeOut = $("probe-out");
      if (probeOut && cmd === "probe-8080") probeOut.textContent = text;
      var probeTag = $("probe-tag");
      if (probeTag && cmd === "probe-8080") {
        probeTag.textContent = isErr ? "unreachable" : (data.status || "ok");
        probeTag.className = "tag " + (isErr ? "err" : "ok");
      }
      toast(title + (isErr ? " failed" : " executed"));
      refreshTelemetryOnce();
      loadLiveDataLogs();
    }

    if (cmd === "probe-8080") {
      api("/api/hermes/probe", { method: "POST", body: { allow_simulation: false } })
        .then(function (res) { logOut("POST /api/hermes/probe (Strict Live 8080)", res); })
        .catch(function (err) { logOut("POST /api/hermes/probe", err.message, true); });
    } else if (cmd === "dispatch-alerts") {
      api("/api/alerts/dispatch", { method: "POST" })
        .then(function (res) { logOut("POST /api/alerts/dispatch (SMTP Diode Relay)", res); })
        .catch(function (err) { logOut("POST /api/alerts/dispatch", err.message, true); });
    } else if (cmd === "cycle-ledger") {
      api("/api/offline-ledger/cycle", { method: "POST" })
        .then(function (res) { logOut("POST /api/offline-ledger/cycle (SQLite Atomic Transition)", res); })
        .catch(function (err) { logOut("POST /api/offline-ledger/cycle", err.message, true); });
    } else if (cmd === "e2e-run") {
      var e2eTag = $("e2e-tag");
      if (e2eTag) { e2eTag.textContent = "running…"; e2eTag.className = "tag warn"; }
      api("/api/jev-e2e", { method: "POST", body: { invoice_fixture: "adversarial_fixture.csv", stage_to_outbox: true } })
        .then(function (res) {
          if (e2eTag) { e2eTag.textContent = res.outcome || "done"; e2eTag.className = "tag ok"; }
          renderE2EStages(res.stages || []);
          logOut("POST /api/jev-e2e (5-Stage Invoice to Outbox)", res);
        })
        .catch(function (err) {
          if (e2eTag) { e2eTag.textContent = "error"; e2eTag.className = "tag err"; }
          logOut("POST /api/jev-e2e", err.message, true);
        });
    } else if (cmd === "decide-system1") {
      api("/api/jev-decide", {
        method: "POST",
        body: {
          state: { input: "reconciliation_verification_check" },
          questions: {
            is_safe: { type: "noul", question: "Is input free of injection?" },
            route: { type: "choice", options: ["fast_agent", "human_gate", "offline_script"] },
            priority: { type: "score", levels: ["low", "normal", "high", "critical"] }
          }
        }
      }).then(function (res) { logOut("POST /api/jev-decide (System-One Evaluator)", res); })
        .catch(function (err) { logOut("POST /api/jev-decide", err.message, true); });
    } else if (cmd === "rung-eval") {
      api("/api/jev-rung", {
        method: "POST",
        body: { judgments: { macro_bias: "bullish", system_health: "ok", data_drift: "none" } }
      }).then(function (res) { logOut("POST /api/jev-rung (7 Market Judgments -> Action Rung)", res); })
        .catch(function (err) { logOut("POST /api/jev-rung", err.message, true); });
    } else if (cmd === "cheap-read") {
      api("/api/jev-cheap-read", {
        method: "POST",
        body: { mode: "bool", path: "adversarial_fixture.csv", question: "Does invoice batch contain quarantined rows?" }
      }).then(function (res) { logOut("POST /api/jev-cheap-read (Level 8 File Fact Screen)", res); })
        .catch(function (err) { logOut("POST /api/jev-cheap-read", err.message, true); });
    } else if (cmd === "vault-scout") {
      api("/api/jev-multi-file", {
        method: "POST",
        body: { mode: "scout", targets: "second-brain", question: "Find trading rules and risk limits" }
      }).then(function (res) { logOut("POST /api/jev-multi-file (Level 9 Multi-File Scout)", res); })
        .catch(function (err) { logOut("POST /api/jev-multi-file", err.message, true); });
    } else if (cmd === "rescan-vault") {
      api("/api/os/obsidian/rescan", { method: "POST" })
        .then(function (res) {
          if (STATE.frame) STATE.frame.obsidian = res;
          renderObsidianInspector();
          logOut("POST /api/os/obsidian/rescan (Vault Cache Invalidated)", res);
        })
        .catch(function (err) { logOut("POST /api/os/obsidian/rescan", err.message, true); });
    } else if (cmd === "guardrail-test") {
      var cmdStr = customInput || ($("guardrail-cmd-input") && $("guardrail-cmd-input").value) || "echo 'JEV system check'";
      api("/api/guardrail/bash", { method: "POST", body: { command: cmdStr } })
        .then(function (res) {
          logOut("POST /api/guardrail/bash (L6 Pre-Execution Screen: " + cmdStr + ")", res);
        })
        .catch(function (err) { logOut("POST /api/guardrail/bash", err.message, true); });
    }
  }

  function runEndpointProbe() {
    var box = $("endpoint-probe-list");
    var summaryTag = $("ep-probe-summary");
    if (!box) return;
    if (summaryTag) {
      summaryTag.textContent = "Probing…";
      summaryTag.className = "tag warn";
    }

    var calibratedEndpoints = [
      { ep: "/api/os/telemetry", method: "GET", desc: "Live OS telemetry stream snapshot & node matrix" },
      { ep: "/api/os/obsidian", method: "GET", desc: "Obsidian Second Brain 4-ring notes & wiki-links" },
      { ep: "/api/os/obsidian/rescan", method: "POST", desc: "Invalidates & re-indexes Second Brain vault notes", cmd: "rescan-vault" },
      { ep: "/api/os/board", method: "GET", desc: "Task tracking, calendar day plan, milestones" },
      { ep: "/api/os/inbox", method: "GET", desc: "Read-only offline inbox snapshot & ledger jobs" },
      { ep: "/api/os/outbox", method: "GET", desc: "Staged outreach queue & metadata diode outbox" },
      { ep: "/api/os/docs", method: "GET", desc: "Zero-PII architecture & diode documentation" },
      { ep: "/api/offline-ledger", method: "GET", desc: "Zero-float job ledger inspection (?mode=ro)" },
      { ep: "/api/offline-ledger/cycle", method: "POST", desc: "Executes atomic queued->running->completed transition", cmd: "cycle-ledger" },
      { ep: "/api/alerts", method: "GET", desc: "Sanitized outbox event queue & dispatch logs" },
      { ep: "/api/alerts/dispatch", method: "POST", desc: "Relays outbox metadata transitions via Gmail SMTP", cmd: "dispatch-alerts" },
      { ep: "/api/hermes", method: "GET", desc: "Cached local model status & token usage" },
      { ep: "/api/hermes/probe", method: "POST", desc: "Strict live inference probe on 127.0.0.1:8080", cmd: "probe-8080" },
      { ep: "/api/guardrail/bash", method: "POST", desc: "Level 6 pre-execution destructive command gate", cmd: "guardrail-test" },
      { ep: "/api/guardrail/events", method: "GET", desc: "Level 6 security audit log of command gates" },
      { ep: "/api/jev-e2e", method: "POST", desc: "5-Stage invoice to GTM diode pipeline (Levels 3-10)", cmd: "e2e-run" },
      { ep: "/api/jev-agentic/events", method: "GET", desc: "Mark LVI ask_jev agentic execution telemetry" },
      { ep: "/api/omnibus", method: "GET", desc: "Multi-zone agent capability policies & ring contracts" }
    ];

    var origin = window.location.origin || "http://127.0.0.1:5050";

    Promise.all(calibratedEndpoints.map(function (item) {
      var t0 = performance.now();
      var reqOpts = { headers: { Accept: "application/json" } };
      if (item.method === "POST") {
        reqOpts.method = "POST";
        reqOpts.headers["Content-Type"] = "application/json";
        if (item.ep === "/api/hermes/probe") reqOpts.body = JSON.stringify({ allow_simulation: false });
        else if (item.ep === "/api/guardrail/bash") reqOpts.body = JSON.stringify({ command: "echo 'calibrated probe'" });
        else if (item.ep === "/api/jev-e2e") reqOpts.body = JSON.stringify({ stage_to_outbox: true });
        else reqOpts.body = JSON.stringify({});
      }

      return fetch(item.ep, reqOpts).then(function (res) {
        return res.text().then(function (raw) {
          return {
            item: item,
            url: origin + item.ep,
            status: res.status,
            ok: res.ok,
            bytes: raw.length,
            ms: Math.round(performance.now() - t0),
            raw: raw
          };
        });
      }).catch(function () {
        return {
          item: item,
          url: origin + item.ep,
          status: 0,
          ok: false,
          bytes: 0,
          ms: Math.round(performance.now() - t0),
          raw: ""
        };
      });
    })).then(function (results) {
      clear(box);
      var okCount = 0;
      results.forEach(function (r) {
        if (r.ok) okCount += 1;
        var infoDiv = h("div", { className: "ep-info" }, [
          h("div", { className: "ep-line" }, [
            h("span", { className: "method-badge " + r.item.method.toLowerCase(), text: r.item.method }),
            h("span", { className: "ep-url", title: r.url, text: r.item.ep })
          ]),
          h("span", { className: "ep-desc", text: r.item.desc })
        ]);

        var metricsDiv = h("div", { className: "ep-metrics" }, [
          h("span", { className: "muted", text: r.bytes + " B" }),
          h("span", { className: "muted", text: r.ms + " ms" }),
          h("span", { className: "tag " + (r.ok ? "ok" : "err"), text: r.status ? ("HTTP " + r.status) : "ERR" })
        ]);

        var execBtn = h("button", {
          className: "btn sm " + (r.item.method === "POST" ? "go" : ""),
          type: "button",
          text: r.item.method === "POST" ? "⚡ Execute" : "↻ Probe",
          onClick: function () {
            if (r.item.cmd) {
              executeCalibratedCommand(r.item.cmd);
            } else {
              var t1 = performance.now();
              fetch(r.item.ep, { headers: { Accept: "application/json" } }).then(function (res) {
                return res.text().then(function (txt) {
                  var ms1 = Math.round(performance.now() - t1);
                  toast("Probed " + r.item.ep + " (" + res.status + " in " + ms1 + " ms)");
                  var out = $("cmd-console-output");
                  if (out) out.textContent = "[" + new Date().toISOString() + "] PROBE " + r.item.ep + " (HTTP " + res.status + ", " + ms1 + " ms):\n" + txt.slice(0, 2000);
                  runEndpointProbe();
                });
              }).catch(function (err) {
                toast("Probe failed: " + err.message);
              });
            }
          }
        });

        box.appendChild(h("div", { className: "ep-row" }, [infoDiv, metricsDiv, execBtn]));
      });

      if (summaryTag) {
        summaryTag.textContent = okCount + "/" + results.length + " Endpoints Calibrated OK";
        summaryTag.className = "tag " + (okCount === results.length ? "ok" : "warn");
      }
    });
  }

  function loadLiveDataLogs() {
    var list = $("live-data-logs");
    var tag = $("data-logs-tag");
    if (!list) return;

    Promise.all([
      api("/api/jev-e2e/events").catch(function () { return []; }),
      api("/api/guardrail/events").catch(function () { return []; }),
      api("/api/os/inbox").catch(function () { return {}; })
    ]).then(function (arr) {
      var e2eList = Array.isArray(arr[0]) ? arr[0] : [];
      var guardList = Array.isArray(arr[1]) ? arr[1] : [];
      var inboxData = arr[2] || {};
      var entries = [];

      if (STATE.frame && STATE.frame.ts) {
        var hotNodes = Object.keys(STATE.frame.nodes || {}).filter(function (k) {
          return STATE.frame.nodes[k] && STATE.frame.nodes[k].hot;
        });
        entries.push({
          ts: STATE.frame.ts,
          source: "TELEMETRY STREAM",
          badge: "ok",
          title: "Frame hash=" + (STATE.frame.hash || "—") + " · hot=" + (hotNodes.length ? hotNodes.join(",") : "none"),
          detail: "Outbox review=" + ((STATE.frame.counters && STATE.frame.counters.outbox_review) || 0) +
                  " · Inbox=" + ((STATE.frame.counters && STATE.frame.counters.inbox) || 0)
        });
      }

      e2eList.slice(0, 3).forEach(function (ev) {
        entries.push({
          ts: ev.timestamp_utc || "",
          source: "E2E PIPELINE",
          badge: ev.outcome === "done" ? "ok" : "info",
          title: "Outcome=" + (ev.outcome || "done") + " (" + ((ev.stages || []).length) + " stages)",
          detail: (ev.stages && ev.stages[3] && ev.stages[3].summary) ? ev.stages[3].summary : "Pipeline verification complete"
        });
      });

      guardList.slice(-4).reverse().forEach(function (g) {
        entries.push({
          ts: g.timestamp_utc || "",
          source: "JEV L6 GUARDRAIL",
          badge: g.allowed ? "ok" : "warn",
          title: (g.allowed ? "ALLOW: " : "BLOCK: ") + (g.command || ""),
          detail: g.reason || ""
        });
      });

      (inboxData.events || []).slice(0, 2).forEach(function (inb) {
        entries.push({
          ts: inb.recorded_at || "",
          source: "INBOX DIODE",
          badge: "info",
          title: inb.event_id + " [" + inb.state + "]",
          detail: "ref=" + inb.reference
        });
      });

      entries.sort(function (a, b) {
        return String(b.ts).localeCompare(String(a.ts));
      });

      clear(list);
      entries.slice(0, 8).forEach(function (item) {
        list.appendChild(h("li", {}, [
          h("div", { className: "card-h" }, [
            h("span", { className: "mono", text: "[" + item.source + "] " + item.title }),
            h("span", { className: "tag " + item.badge, text: item.ts })
          ]),
          h("div", { className: "muted", text: item.detail })
        ]));
      });

      if (tag) {
        tag.textContent = entries.length + " live entries";
      }
    });
  }

  function renderE2EStages(stages) {
    var list = $("e2e-stages");
    if (!list) return;
    clear(list);
    stages.forEach(function (s) {
      list.appendChild(h("li", {}, [
        h("div", { className: "mono", text: "Stage " + s.stage + " · " + s.jev_level + " [" + s.outcome + "]" }),
        h("div", { className: "muted", text: s.summary || "" })
      ]));
    });
  }

  function loadSystemLogs() {
    api("/api/jev-e2e/events").then(function (events) {
      if (Array.isArray(events) && events.length) {
        renderE2EStages(events[0].stages || []);
      }
    }).catch(function () {});

    api("/api/guardrail/events").then(function (events) {
      var list = $("guard-list");
      var tag = $("guard-tag");
      if (!list || !Array.isArray(events)) return;
      if (tag) tag.textContent = events.length + " recorded";
      clear(list);
      events.slice(-8).reverse().forEach(function (ev) {
        list.appendChild(h("li", {}, [
          h("div", { className: "mono", text: (ev.allowed ? "ALLOW: " : "BLOCK: ") + (ev.command || "") }),
          h("div", { className: "muted", text: (ev.reason || "") + " · " + (ev.timestamp_utc || "") })
        ]));
      });
    }).catch(function () {});

    loadLiveDataLogs();
  }

  // ==================== MODAL SHEETS (INBOX, OUTBOX, ALERTS, EDITOR, DOCS) ====================
  function openSheet(kind, arg) {
    var scrim = $("scrim");
    var sheet = $("sheet");
    var title = $("sheet-title");
    var actions = $("sheet-actions");
    var body = $("sheet-body");
    if (!scrim || !sheet || !title || !actions || !body) return;

    clear(actions);
    clear(body);
    scrim.removeAttribute("hidden");
    sheet.removeAttribute("hidden");

    if (kind === "inbox") {
      title.textContent = "Inbox Diode // offline_snapshot.json";
      renderInboxSheet(body);
    } else if (kind === "outbox") {
      title.textContent = "Outbox Diode // Human Review Gate & Notification Relay";
      renderOutboxSheet(body, actions);
    } else if (kind === "alerts") {
      title.textContent = "Active System Alerts";
      renderAlertsSheet(body);
    } else if (kind === "editor") {
      title.textContent = "Quick Code Editor // hud-interface/scratch/";
      renderEditorSheet(body, actions, arg);
    } else if (kind === "docs") {
      title.textContent = "Documentation & Second Brain Reader";
      renderDocsSheet(body, actions, arg);
    }
  }

  function closeSheet() {
    var scrim = $("scrim");
    var sheet = $("sheet");
    if (scrim) scrim.setAttribute("hidden", "");
    if (sheet) sheet.setAttribute("hidden", "");
  }

  function renderInboxSheet(body) {
    body.appendChild(h("p", { className: "hint", text: "Loading inbox snapshot…" }));
    api("/api/os/inbox").then(function (data) {
      clear(body);
      body.appendChild(h("div", { className: "mono muted", text: "Source: " + data.source + " · Exported: " + (data.exported_at || "—") }));

      var events = data.events || [];
      body.appendChild(h("div", { className: "sub-label", text: "Observed Diode Events (" + events.length + ")" }));
      events.forEach(function (ev) {
        body.appendChild(h("div", { className: "draft-card" }, [
          h("div", { className: "mono", text: ev.event_id + " · state=" + ev.state }),
          h("div", { className: "muted mono", text: "ref=" + ev.reference + " · " + ev.recorded_at })
        ]));
      });

      var jobs = data.jobs || [];
      body.appendChild(h("div", { className: "sub-label", text: "Snapshot Ledger Jobs (" + jobs.length + ")" }));
      jobs.forEach(function (j) {
        body.appendChild(h("div", { className: "draft-card" }, [
          h("div", { className: "mono", text: j.job_id + " (" + j.job_type + ") → " + j.state }),
          h("div", { className: "muted mono", text: "attempts=" + j.attempt_count + " · updated=" + j.updated_at })
        ]));
      });
    }).catch(function (err) {
      clear(body);
      body.appendChild(h("p", { className: "hint", text: "Error: " + err.message }));
    });
  }

  function renderOutboxSheet(body, actions) {
    body.appendChild(h("p", { className: "hint", text: "Loading outbox queues…" }));
    actions.appendChild(h("button", {
      className: "btn sm",
      type: "button",
      text: "Flush Notification Outbox (SMTP)",
      onClick: function () {
        api("/api/alerts/dispatch", { method: "POST", body: {} }).then(function () {
          toast("Notification outbox relay triggered");
          renderOutboxSheet(body, clear(actions) || actions);
          refreshTelemetryOnce();
        }).catch(function (err) {
          toast("Relay error: " + err.message);
        });
      }
    }));

    api("/api/os/outbox").then(function (data) {
      clear(body);
      body.appendChild(h("div", { className: "hint", text: data.notice || "" }));
      body.appendChild(h("div", {
        className: "mono muted",
        text: "Notification Outbox: " + (data.notify_pending || []).length + " pending · " + (data.notify_archived || 0) + " archived"
      }));

      var drafts = data.drafts || [];
      body.appendChild(h("div", { className: "sub-label", text: "Staged GTM Outreach Drafts (" + drafts.length + ")" }));
      drafts.forEach(function (d) {
        var stClass = d.status === "approved" ? "ok" : (d.status === "rejected" ? "err" : "warn");
        var btnRow = h("div", { className: "add-row" });
        if (d.status === "needs_review" && data.revision) {
          btnRow.appendChild(h("button", {
            className: "btn ok sm",
            type: "button",
            text: "Approve (Record Decision)",
            onClick: function () {
              decideOutbox(d.id, data.revision, "approved", body, actions);
            }
          }));
          btnRow.appendChild(h("button", {
            className: "btn danger sm",
            type: "button",
            text: "Reject",
            onClick: function () {
              decideOutbox(d.id, data.revision, "rejected", body, actions);
            }
          }));
        }

        body.appendChild(h("div", { className: "draft-card" }, [
          h("div", { className: "card-h" }, [
            h("strong", { text: d.company + (d.contact ? " · " + d.contact : "") }),
            h("span", { className: "tag " + stClass, text: d.status })
          ]),
          h("div", { className: "mono", text: d.subject }),
          h("pre", { className: "mono-box", text: d.body }),
          btnRow
        ]));
      });
    }).catch(function (err) {
      clear(body);
      body.appendChild(h("p", { className: "hint", text: "Error: " + err.message }));
    });
  }

  function decideOutbox(id, revision, decision, body, actions) {
    api("/api/os/outbox/decide", {
      method: "POST",
      body: { id: id, revision: revision, decision: decision }
    }).then(function () {
      toast("Recorded decision: " + decision);
      clear(actions);
      renderOutboxSheet(body, actions);
      refreshTelemetryOnce();
    }).catch(function (err) {
      toast(err.message);
    });
  }

  function renderAlertsSheet(body) {
    var alerts = (STATE.frame && STATE.frame.alerts) || [];
    if (!alerts.length) {
      body.appendChild(h("p", { className: "hint", text: "Zero active alerts." }));
      return;
    }
    alerts.forEach(function (a) {
      body.appendChild(h("div", {
        className: "alert-row " + (a.severity || "info"),
        onClick: function () {
          closeSheet();
          handleAlertClick(a);
        }
      }, [
        h("div", { className: "alert-head" }, [
          h("span", { text: a.title }),
          h("span", { className: "tag " + (a.severity === "crit" ? "err" : a.severity), text: a.severity.toUpperCase() })
        ]),
        h("div", { className: "alert-detail", text: a.detail })
      ]));
    });
  }

  function renderEditorSheet(body, actions, initialFile) {
    var nameInput = h("input", { placeholder: "notes.md or script.py", value: initialFile || "scratch_notes.md" });
    var area = h("textarea", { className: "editor-area", placeholder: "Write code or notes here (saved strictly inside hud-interface/scratch/)…" });
    var statusEl = h("span", { className: "mono muted", text: "Ready" });
    var baseSha = null;

    function openFile(fname) {
      nameInput.value = fname;
      api("/api/os/editor/file?name=" + encodeURIComponent(fname)).then(function (res) {
        area.value = res.text || "";
        baseSha = res.sha256 || null;
        statusEl.textContent = "Loaded " + res.name + " (" + res.bytes + " B)";
      }).catch(function () {
        area.value = "";
        baseSha = null;
        statusEl.textContent = "New file: " + fname;
      });
    }

    var fileBar = h("div", { className: "chip-row" });
    api("/api/os/editor/files").then(function (res) {
      (res.files || []).forEach(function (f) {
        fileBar.appendChild(h("button", {
          className: "chip",
          type: "button",
          text: f.name,
          onClick: function () { openFile(f.name); }
        }));
      });
    });

    actions.appendChild(h("button", {
      className: "btn go sm",
      type: "button",
      text: "Save (Atomic)",
      onClick: function () {
        var fname = nameInput.value.trim();
        if (!fname) return;
        api("/api/os/editor/save", {
          method: "POST",
          body: { name: fname, text: area.value, base_sha256: baseSha }
        }).then(function (res) {
          baseSha = res.sha256;
          statusEl.textContent = "Saved " + res.name + " at " + res.saved_at;
          toast("Saved " + res.name);
          loadDocsAndScratch();
          refreshTelemetryOnce();
        }).catch(function (err) {
          toast(err.message);
        });
      }
    }));

    body.appendChild(fileBar);
    body.appendChild(h("div", { className: "add-row" }, [
      h("label", { className: "field", text: "File:" }),
      nameInput,
      statusEl
    ]));
    body.appendChild(area);

    openFile(nameInput.value);
  }

  function renderDocsSheet(body, actions, initialId) {
    var chipBar = h("div", { className: "chip-row" });
    var viewer = h("pre", { className: "mono-box", text: "Select a document above to read it." });
    var pathMeta = h("div", { className: "mono muted" });

    function loadDoc(docId) {
      api("/api/os/doc?id=" + encodeURIComponent(docId)).then(function (res) {
        pathMeta.textContent = res.title + " — " + res.path + " (" + res.bytes + " bytes)";
        viewer.textContent = res.text || "";
      }).catch(function (err) {
        viewer.textContent = "Could not read document: " + err.message;
      });
    }

    (STATE.docs || []).forEach(function (d) {
      if (!d.available) return;
      chipBar.appendChild(h("button", {
        className: "chip",
        type: "button",
        text: d.group + ": " + d.title,
        onClick: function () { loadDoc(d.id); }
      }));
    });

    body.appendChild(chipBar);
    body.appendChild(pathMeta);
    body.appendChild(viewer);

    var targetId = initialId || (STATE.docs[0] && STATE.docs[0].id);
    if (targetId) loadDoc(targetId);
  }

  // ==================== QUARANTINE DRAWER & AUTO-RECOVERY ====================
  function loadQuarantineDrawer() {
    var tbody = $("quar-table-body");
    var liveMsg = $("quar-live-msg");
    if (liveMsg) liveMsg.textContent = "Loading live quarantine rows from CSV...";

    api("/api/quarantine").then(function (res) {
      if (!res || !res.rows) {
        if (liveMsg) liveMsg.textContent = "Failed to load quarantine data.";
        return;
      }

      var metrics = res.metrics || {};
      var inv = res.invariant || {};

      var countTag = $("quar-badge-count");
      if (countTag) {
        countTag.textContent = (metrics.quarantined || 0) + " Quarantined";
        countTag.className = "tag " + ((metrics.quarantined || 0) > 0 ? "warn" : "ok");
      }

      var invTag = $("quar-badge-invariant");
      if (invTag) {
        invTag.textContent = "Invariant: " + (inv.passed ? "PASS" : "BREACH");
        invTag.className = "tag " + (inv.passed ? "ok" : "err");
      }

      var formulaTxt = $("quar-formula-txt");
      if (formulaTxt) {
        formulaTxt.textContent = inv.formula || (metrics.received + " == " + metrics.accepted + " + " + metrics.quarantined + " + " + metrics.duplicates);
      }

      var formulaBadge = $("quar-formula-badge");
      var banner = $("quar-status-banner");
      if (formulaBadge) {
        formulaBadge.textContent = inv.passed ? "PASS" : "BREACH";
        formulaBadge.className = "chip-badge " + (inv.passed ? "ok" : "err");
      }
      if (banner) {
        banner.classList.toggle("pass", Boolean(inv.passed && !metrics.quarantined));
      }

      if (liveMsg) {
        liveMsg.textContent = "Fixture: " + (res.fixture || "adversarial_fixture.csv") + " · " + metrics.received + " rows parsed.";
      }

      renderQuarantineTable(res.rows);
    }).catch(function (err) {
      if (liveMsg) liveMsg.textContent = "Error: " + err.message;
    });
  }

  function renderQuarantineTable(rows) {
    var tbody = $("quar-table-body");
    if (!tbody) return;
    clear(tbody);

    if (!rows || !rows.length) {
      var emptyTr = h("tr", {}, [
        h("td", { colSpan: "6", className: "hint", text: "No rows found in fixture." })
      ]);
      tbody.appendChild(emptyTr);
      return;
    }

    rows.forEach(function (r) {
      var isQ = r.status === "quarantined";
      var isDup = r.status === "duplicate";
      var rowCls = isQ ? "row-quarantined" : (isDup ? "row-duplicate" : "");

      var amtCls = "mono" + (r.is_malformed || isQ ? " bad-val" : "");
      var statusTagCls = "tag " + (isQ ? "err" : (isDup ? "warn" : "ok"));

      var actionsTd = h("td", { className: "quar-actions-cell" }, [
        h("button", {
          className: "btn sm",
          type: "button",
          text: "✏️ Edit",
          title: "In-browser edit row",
          onClick: function () { openQuarantineRowEditor(r); }
        })
      ]);

      if (r.is_malformed || isQ) {
        actionsTd.appendChild(h("button", {
          className: "btn go sm quar-autofix-btn",
          type: "button",
          text: "⚡ Auto-Fix",
          title: "Auto-fix penny fraction or negative sign",
          onClick: function () { autoFixSingleRow(r.row_idx); }
        }));
      }

      var tr = h("tr", { className: rowCls }, [
        h("td", { className: "mono muted", text: String(r.row_idx) }),
        h("td", { className: "mono", text: r.invoice_id }),
        h("td", { className: amtCls, text: r.amount }),
        h("td", { className: "mono muted", text: r.date || "—" }),
        h("td", {}, [
          h("span", { className: statusTagCls, text: r.status.toUpperCase() }),
          r.reason ? h("span", { className: "muted sm-txt quar-reason-txt", text: r.reason }) : null
        ]),
        actionsTd
      ]);

      tbody.appendChild(tr);
    });
  }

  function openQuarantineRowEditor(row) {
    var card = $("quar-edit-card");
    if (!card) return;
    $("quar-edit-row-idx").textContent = row.row_idx;
    $("quar-form-row").value = row.row_idx;
    $("quar-form-invoice").value = row.invoice_id;
    $("quar-form-amount").value = row.amount;
    $("quar-form-date").value = row.date;
    card.removeAttribute("hidden");
    card.scrollIntoView({ behavior: "smooth" });
  }

  function autoFixSingleRow(rowIdx) {
    var liveMsg = $("quar-live-msg");
    if (liveMsg) liveMsg.textContent = "Auto-recovering Row " + rowIdx + "...";

    api("/api/quarantine/repair", {
      method: "POST",
      body: { row_idx: rowIdx, auto_recover: true }
    }).then(function (res) {
      if (res && res.status === "ok") {
        toast("Row " + rowIdx + " successfully repaired!");
        loadQuarantineDrawer();
      } else {
        toast("Failed: " + (res.error || "Unknown error"));
      }
    }).catch(function (err) {
      toast("Error: " + err.message);
    });
  }

  function autoRecoverAllQuarantine() {
    var liveMsg = $("quar-live-msg");
    if (liveMsg) liveMsg.textContent = "Auto-recovering all malformed penny rows...";

    api("/api/quarantine/repair", {
      method: "POST",
      body: { auto_recover_all: true }
    }).then(function (res) {
      if (res && res.status === "ok") {
        toast("All malformed rows auto-recovered and re-parsed!");
        loadQuarantineDrawer();
      } else {
        toast("Failed: " + (res.error || "Unknown error"));
      }
    }).catch(function (err) {
      toast("Error: " + err.message);
    });
  }

  function resetQuarantineFixture() {
    var liveMsg = $("quar-live-msg");
    if (liveMsg) liveMsg.textContent = "Resetting fixture to baseline test state...";

    api("/api/quarantine/reset", { method: "POST" }).then(function (res) {
      toast("Fixture reset to baseline state.");
      loadQuarantineDrawer();
    }).catch(function (err) {
      toast("Reset error: " + err.message);
    });
  }

  function wireQuarantineDrawer() {
    var btnReparse = $("quar-btn-reparse");
    if (btnReparse) {
      btnReparse.addEventListener("click", function () {
        loadQuarantineDrawer();
      });
    }

    var btnAutoRecoverAll = $("quar-btn-autorecover-all");
    if (btnAutoRecoverAll) {
      btnAutoRecoverAll.addEventListener("click", function () {
        autoRecoverAllQuarantine();
      });
    }

    var btnReset = $("quar-btn-reset-fixture");
    if (btnReset) {
      btnReset.addEventListener("click", function () {
        resetQuarantineFixture();
      });
    }

    var btnCancel = $("quar-edit-cancel");
    if (btnCancel) {
      btnCancel.addEventListener("click", function () {
        var card = $("quar-edit-card");
        if (card) card.setAttribute("hidden", "");
      });
    }

    var btnAutoFixPenny = $("quar-form-auto-fix");
    if (btnAutoFixPenny) {
      btnAutoFixPenny.addEventListener("click", function () {
        var amtInput = $("quar-form-amount");
        if (!amtInput) return;
        var val = amtInput.value.trim().replace(/^-+/, "");
        var parts = val.split(".");
        if (parts.length === 2) {
          var dec = (parts[1] + "00").slice(0, 2);
          amtInput.value = (parts[0] || "0") + "." + dec;
        } else if (parts.length === 1 && parts[0]) {
          amtInput.value = parts[0] + ".00";
        }
      });
    }

    var editForm = $("quar-edit-form");
    if (editForm) {
      editForm.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var rowIdx = Number($("quar-form-row").value || "0");
        var invoiceId = $("quar-form-invoice").value.trim();
        var amount = $("quar-form-amount").value.trim();
        var dateVal = $("quar-form-date").value.trim();

        var card = $("quar-edit-card");
        var liveMsg = $("quar-live-msg");
        if (liveMsg) liveMsg.textContent = "Saving Row " + rowIdx + " and re-parsing CSV...";

        api("/api/quarantine/repair", {
          method: "POST",
          body: {
            row_idx: rowIdx,
            invoice_id: invoiceId,
            amount: amount,
            date: dateVal
          }
        }).then(function (res) {
          if (res && res.status === "ok") {
            toast("Row " + rowIdx + " saved & re-parsed!");
            if (card) card.setAttribute("hidden", "");
            loadQuarantineDrawer();
          } else {
            toast("Save failed: " + (res.error || "Unknown error"));
          }
        }).catch(function (err) {
          toast("Save error: " + err.message);
        });
      });
    }
  }

  // ==================== BOOTSTRAP ====================
  document.addEventListener("DOMContentLoaded", function () {
    wireNavigation();
    wireBoardForms();
    wireObsidianWidget();
    wireSystemsView();
    wireQuarantineDrawer();
    updateClock();
    setInterval(updateClock, 1000);
    loadBoard();
    loadDocsAndScratch();
    connectTelemetryStream();
  });
})();
