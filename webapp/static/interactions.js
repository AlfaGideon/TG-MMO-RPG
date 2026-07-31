/*
 * Shadow Lands — интерактивные редакторы админ-панели (стек A, GitHub Pages).
 *
 * Раньше эта логика жила как <script> ВНУТРИ HTML-разметки, которую Python
 * (webapp/pages/world_map.py, world_grid.py, dungeons.py) вставлял через
 * `node.innerHTML = markup`. Браузеры по спецификации НЕ выполняют <script>,
 * попавшие в DOM через innerHTML (https://developer.mozilla.org/.../innerHTML) —
 * поэтому кисть по карте, drag-and-drop локаций и live-таймер порталов
 * реально не работали ни разу, хотя код выглядел рабочим и проходил все
 * текстовые тесты (они проверяют HTML-строку, не выполнение в браузере).
 * Это и есть главная причина «кривой» работы панели.
 *
 * Исправление: весь интерактив живёт здесь, в настоящем статическом JS,
 * подключённом обычным <script src=...> (выполняется один раз при
 * загрузке страницы). Слушатели вешаются ДЕЛЕГИРОВАННО на document —
 * поэтому продолжают работать после любого количества `render()`
 * (Python переставляет содержимое #view через innerHTML, слушатели на
 * самом document это не касается).
 *
 * Правило границы: этот файл не считает игровые правила и не хранит
 * состояние мира — только жесты мыши/касаний конвертирует в вызовы
 * window.__app.* (Python, engine/webapp/app.py), который уже проверен
 * тестами (test_pages.py, test_wiring.py). Тяжёлая работа (полный
 * ре-рендер) не делается на каждое движение мыши: наведение при
 * рисовании красит только сам DOM-узел на месте (см. app.paint_cell →
 * app._repaint_cell), Python вызывается один раз на клетку, а не на
 * каждое пиксельное событие mousemove.
 */
(function () {
  "use strict";

  function app() {
    return window.__app || null;
  }

  // ── Карта локации: кисть, режимы, пипетка ──────────────────────────
  // Состояние живёт на самом DOM-узле сетки (dataset), поэтому свежая
  // сетка после полного render() всегда начинает с режима «рисование» —
  // ровно так вело бы себя изначально задуманное поведение.
  let painting = false;

  function paintBrush() {
    const sel = document.getElementById("paintBrush");
    return sel ? sel.value : "grass";
  }

  function gridMode(grid) {
    return grid.dataset.mode || "paint";
  }

  function setGridMode(grid, mode) {
    grid.dataset.mode = mode;
    grid.style.cursor = mode === "paint" ? "crosshair" : "pointer";
    const paintBtn = document.getElementById("modePaint");
    const inspectBtn = document.getElementById("modeInspect");
    if (paintBtn) paintBtn.classList.toggle("primary", mode === "paint");
    if (inspectBtn) inspectBtn.classList.toggle("primary", mode === "inspect");
  }

  function editCell(key) {
    const a = app();
    if (a && a.edit_cell) a.edit_cell(key);
  }

  function paintCell(key) {
    const brush = paintBrush();
    // Дверь и объекты правятся в боковом редакторе — там есть цель перехода.
    if (brush === "door") { editCell(key); return; }
    const a = app();
    if (a && a.paint_cell) a.paint_cell(key, brush);
  }

  document.addEventListener("click", function (e) {
    const brushBtn = e.target.closest("[data-brush]");
    if (brushBtn) {
      const b = brushBtn.dataset.brush;
      const sel = document.getElementById("paintBrush");
      if (sel) sel.value = b;
      const lbl = document.getElementById("brushLabel");
      if (lbl) lbl.textContent = b;
      document.querySelectorAll("[data-brush]").forEach(function (x) {
        x.classList.remove("primary");
      });
      brushBtn.classList.add("primary");
      const a = app();
      if (a && a.set_brush) a.set_brush(b);
      return;
    }
    if (e.target.closest("#modePaint")) {
      const grid = document.getElementById("locMapGrid");
      if (grid) setGridMode(grid, "paint");
      return;
    }
    if (e.target.closest("#modeInspect")) {
      const grid = document.getElementById("locMapGrid");
      if (grid) setGridMode(grid, "inspect");
      return;
    }
  });

  document.addEventListener("mousedown", function (e) {
    const grid = e.target.closest("#locMapGrid");
    if (!grid || e.button === 2) return;
    const cell = e.target.closest(".c");
    if (!cell) return;
    e.preventDefault();
    if (gridMode(grid) !== "paint") { editCell(cell.dataset.key); return; }
    painting = true;
    paintCell(cell.dataset.key);
  });

  document.addEventListener("mouseover", function (e) {
    if (!painting) return;
    const grid = e.target.closest("#locMapGrid");
    if (!grid || gridMode(grid) !== "paint") return;
    const cell = e.target.closest(".c");
    if (cell) paintCell(cell.dataset.key);
  });

  document.addEventListener("mouseup", function () { painting = false; });

  document.addEventListener("contextmenu", function (e) {
    const grid = e.target.closest("#locMapGrid");
    if (!grid) return;
    const cell = e.target.closest(".c");
    if (!cell) return;
    e.preventDefault();
    editCell(cell.dataset.key);
  });

  document.addEventListener("auxclick", function (e) {
    if (e.button !== 1) return;
    const grid = e.target.closest("#locMapGrid");
    if (!grid) return;
    const cell = e.target.closest(".c");
    if (!cell) return;
    e.preventDefault();
    const a = app();
    if (a && a.pick_brush) a.pick_brush(cell.dataset.key);
  });

  // ── Глобальная сетка мира: drag-and-drop локаций ───────────────────
  let draggedIdx = null;

  document.addEventListener("dragstart", function (e) {
    const cell = e.target.closest("#worldGrid .loc-cell");
    if (!cell) return;
    const parts = (cell.dataset.arg || "").split(":");
    draggedIdx = parts[2] !== undefined ? parts[2] : null;
    cell.style.opacity = "0.4";
    if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
  });

  document.addEventListener("dragend", function (e) {
    const cell = e.target.closest("#worldGrid .loc-cell");
    if (cell) cell.style.opacity = "";
  });

  document.addEventListener("dragover", function (e) {
    const grid = e.target.closest("#worldGrid");
    if (!grid) return;
    e.preventDefault();
    const cell = e.target.closest(".c");
    if (cell) cell.style.outline = "2px dashed var(--accent)";
  });

  document.addEventListener("dragleave", function (e) {
    const grid = e.target.closest("#worldGrid");
    if (!grid) return;
    const cell = e.target.closest(".c");
    if (cell) cell.style.outline = "";
  });

  document.addEventListener("drop", function (e) {
    const grid = e.target.closest("#worldGrid");
    if (!grid || draggedIdx === null) return;
    const cell = e.target.closest(".c");
    if (!cell) return;
    e.preventDefault();
    cell.style.outline = "";
    const parts = (cell.dataset.arg || "").split(":");
    if (parts.length < 2) { draggedIdx = null; return; }
    const a = app();
    if (a && a.move_world_loc) a.move_world_loc(draggedIdx, parts[0], parts[1]);
    draggedIdx = null;
  });

  // ── Живой таймер порталов подземелий ───────────────────────────────
  // `.live-timer[data-opened][data-duration]` — момент открытия (unix,
  // секунды) и общая длительность жизни портала. Формат общий с
  // `.cata-timer[data-until]` (webapp/live_timer.py), который тикает из
  // Python через js.setInterval — там таймер завязан на игровые данные
  // (webapp.pages.world_cataclysms), а этот — на чистую арифметику дат,
  // поэтому ему не нужен Python вообще.
  function fmtLeft(seconds) {
    if (seconds <= 0) return "⏰ Закрыт";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return "⏳ " + h + "ч " + m + "м " + s + "с";
  }

  function tickDungeonTimers() {
    document.querySelectorAll(".live-timer[data-opened]").forEach(function (el) {
      const opened = parseFloat(el.dataset.opened || "0");
      const duration = parseFloat(el.dataset.duration || "7200");
      if (!opened) { el.textContent = "—"; return; }
      const left = duration - Math.floor(Date.now() / 1000 - opened);
      el.textContent = left <= 0 ? "🚫 Авто-закрыт" : fmtLeft(left);
    });
  }
  setInterval(tickDungeonTimers, 1000);
  tickDungeonTimers();
})();
