/* Теневые Земли — клиент игрового API.
   Работает и в Telegram Mini App (авто-вход по initData), и в APK WebView
   (вход одноразовым кодом из бота). Токен живёт в localStorage этого origin. */
(function () {
  "use strict";

  var API = "/api/player";
  var TOKEN_KEY = "sl_player_token";
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  var $ = function (id) { return document.getElementById(id); };
  var state = { token: localStorage.getItem(TOKEN_KEY) || "", battle: null };

  // ── Тосты ────────────────────────────────────────────────────────
  var toastTimer = null;
  function toast(msg, kind) {
    var el = $("toast");
    el.textContent = msg;
    el.className = "toast show " + (kind || "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.className = "toast"; }, 2600);
  }

  // ── API ──────────────────────────────────────────────────────────
  async function api(path, method, body) {
    var opts = { method: method || "GET", headers: {} };
    if (state.token) opts.headers.Authorization = "Bearer " + state.token;
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    var resp = await fetch(API + path, opts);
    var data = await resp.json().catch(function () { return {}; });
    if (resp.status === 401) {
      logout();
      throw new Error(data.error || "Сессия истекла");
    }
    if (!resp.ok || data.ok === false) {
      throw new Error(data.error || ("Ошибка сервера (" + resp.status + ")"));
    }
    return data;
  }

  function logout() {
    state.token = "";
    localStorage.removeItem(TOKEN_KEY);
    $("game").hidden = true;
    $("login").hidden = false;
  }

  // ── Вход ─────────────────────────────────────────────────────────
  async function loginWith(payload, endpoint) {
    var status = $("loginStatus");
    status.hidden = true;
    $("loginBtn").disabled = true;
    try {
      var data = await fetch(API + endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(function (r) { return r.json(); });
      if (!data.ok) throw new Error(data.error || "Вход не удался");
      state.token = data.token;
      localStorage.setItem(TOKEN_KEY, data.token);
      if (!data.has_character) {
        toast("Сначала создай героя в боте", "err");
      }
      enterGame();
    } catch (e) {
      status.textContent = "⛔ " + e.message;
      status.hidden = false;
    } finally {
      $("loginBtn").disabled = false;
    }
  }

  async function tryTelegramLogin() {
    if (!tg || !tg.initData) return false;
    tg.ready();
    tg.expand();
    try {
      await loginWith({ initData: tg.initData }, "/auth/telegram");
      return true;
    } catch (e) {
      return false; // остаёмся на экране кода
    }
  }

  // ── Навигация по вкладкам ────────────────────────────────────────
  function switchTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) {
      t.hidden = t.id !== "tab-" + name;
    });
    document.querySelectorAll(".nav-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.tab === name);
    });
    if (name === "profile") loadProfile();
    if (name === "map") loadCell();
    if (name === "inventory") loadInventory();
    if (name === "battle") refreshBattleTab();
  }

  // ── Профиль ──────────────────────────────────────────────────────
  function barPct(cur, max) { return Math.max(0, Math.min(100, (cur / Math.max(1, max)) * 100)); }

  async function loadProfile() {
    var card = $("profileCard");
    try {
      var data = await api("/me");
      if (!data.has_character) {
        card.innerHTML = '<div class="empty">Персонаж ещё не создан.<br>Открой бота и пройди создание героя, затем вернись сюда.</div>';
        return;
      }
      var p = data.profile;
      $("heroName").textContent = p.name;
      $("heroLevel").textContent = "ур. " + p.level;
      $("hpBar").style.width = barPct(p.hp.current, p.hp.max) + "%";
      $("hpText").textContent = p.hp.current + "/" + p.hp.max;
      var stats = p.stats;
      card.innerHTML =
        '<div class="profile-head">' +
          '<img class="profile-avatar" src="/static/branding/start_ru.png" alt="">' +
          '<div><div class="profile-name">' + esc(p.name) + '</div>' +
          '<div class="profile-class">' + esc(p.class) + (p.faction ? " · " + esc(p.faction) : "") + '</div>' +
          '<div class="muted">' + esc(p.currency) + '</div></div>' +
        '</div>' +
        '<div class="stat-grid">' +
          statBox("❤️ Здоровье", p.hp.current + "/" + p.hp.max) +
          statBox("💙 Мана", p.mp.current + "/" + p.mp.max) +
          statBox("💪 Сила", stats.strength) + statBox("🏃 Ловкость", stats.agility) +
          statBox("🧠 Интеллект", stats.intelligence) + statBox("🛡 Выносливость", stats.endurance) +
          statBox("🍀 Удача", stats.luck) + statBox("🎯 Очки", p.stat_points) +
        '</div>' +
        '<div class="xp-row"><div class="xp-label"><span>Опыт</span><span>' +
          p.experience + " / " + p.exp_to_next + '</span></div>' +
          '<div class="bar"><div class="bar-fill xp" style="width:' + barPct(p.experience, p.exp_to_next) + '%"></div></div></div>' +
        (p.location ? '<p class="muted" style="margin-top:.9rem">📍 ' + esc(p.location) + "</p>" : "");
    } catch (e) {
      card.innerHTML = '<div class="empty">' + esc(e.message) + "</div>";
    }
  }
  function statBox(k, v) {
    return '<div class="stat-box"><div class="k">' + k + '</div><div class="v">' + v + "</div></div>";
  }

  // ── Карта и клетка ───────────────────────────────────────────────
  async function loadCell() {
    try {
      var data = await api("/cell");
      renderCell(data.cell);
    } catch (e) { toast(e.message, "err"); }
  }

  function renderCell(cell) {
    $("locName").textContent = cell.location;
    $("locCoords").textContent = "[" + cell.cell.x + "," + cell.cell.y + "]" +
      (cell.cell.floor ? " эт." + cell.cell.floor : "");
    $("cellDesc").textContent = cell.cell.description || "Тихое место.";
    var tags = [];
    if (cell.mob) tags.push('<span class="tag">👹 ' + esc(cell.mob.name) + " ур." + cell.mob.level + "</span>");
    if (cell.npc) tags.push('<span class="tag">💬 ' + esc(cell.npc.name) + "</span>");
    if (cell.chest && cell.chest.ready) tags.push('<span class="tag">📦 Сундук</span>');
    if (cell.campfire) tags.push('<span class="tag">🔥 Костёр</span>');
    if (cell.house) tags.push('<span class="tag">🏠 Дом</span>');
    $("cellTags").innerHTML = tags.join("") || '<span class="tag">Пусто</span>';

    var byDir = {};
    cell.neighbors.forEach(function (n) { byDir[n.direction] = n; });
    document.querySelectorAll(".dpad-btn").forEach(function (btn) {
      btn.disabled = !byDir[btn.dataset.dir];
    });

    var mobCard = $("mobCard");
    if (cell.mob && !cell.mob.engaged) {
      mobCard.hidden = false;
      $("mobInfo").innerHTML =
        '<div class="mob-row"><div><div class="name">' + esc(cell.mob.name) + '</div>' +
        '<div class="meta">Уровень ' + cell.mob.level + " · ❤️ " + cell.mob.hp + "/" + cell.mob.max_hp +
        (cell.mob.is_boss ? " · 👑 БОСС" : "") + "</div></div></div>";
    } else {
      mobCard.hidden = true;
    }
  }

  async function move(dir) {
    try {
      var data = await api("/move", "POST", { direction: dir });
      renderCell(data.cell);
      toast(data.message || "Шаг", "ok");
    } catch (e) { toast(e.message, "err"); }
  }

  async function inspect() {
    try {
      var data = await api("/inspect", "POST");
      var msg = data.message;
      if (data.loot && data.loot.length) msg += " 🎁 " + data.loot.join(", ");
      toast(msg, "ok");
      if (data.cell) renderCell(data.cell);
    } catch (e) { toast(e.message, "err"); }
  }

  async function rest() {
    try {
      var data = await api("/rest", "POST");
      toast(data.message, "ok");
      loadProfile();
    } catch (e) { toast(e.message, "err"); }
  }

  // ── Бой ──────────────────────────────────────────────────────────
  function renderBattle(r) {
    state.battle = r;
    if (r.mob) {
      $("battleMobName").textContent = r.mob.name;
      $("mobHpBar").style.width = barPct(r.mob.hp, r.mob.max_hp) + "%";
      $("mobHpText").textContent = r.mob.hp + "/" + r.mob.max_hp;
    } else if (r.escaped) {
      $("battleMobName").textContent = "Побег";
      $("mobHpBar").style.width = "0%";
      $("mobHpText").textContent = "";
    }
    if (r.message && (!r.log || r.log.indexOf(r.message) === -1)) {
      r.log = (r.log || []).concat([r.message]);
    }
    var log = $("battleLog");
    log.innerHTML = (r.log || []).map(function (line) {
      return "<p>" + esc(line) + "</p>";
    }).join("");
    log.scrollTop = log.scrollHeight;
    var finished = r.victory || r.defeat || r.escaped;
    $("attackBtn").hidden = finished;
    $("fleeBtn").hidden = finished;
    $("leaveBattleBtn").hidden = !finished;
    if (r.victory) {
      var extra = r.message || "Победа!";
      if (r.gold_bronze) extra += " 💰+" + r.gold_bronze;
      if (r.loot && r.loot.length) extra += " 🎁 " + r.loot.join(", ");
      if (r.levels_gained) extra += " ⬆️ Новый уровень!";
      toast(extra, "ok");
      loadProfile();
    } else if (r.defeat) {
      toast(r.message || "Поражение", "err");
      loadProfile();
    } else if (r.escaped) {
      toast(r.message || "Побег удался", "ok");
    }
  }

  async function refreshBattleTab() {
    try {
      var data = await api("/battle");
      if (data.active && data.state) {
        renderBattle(data.state);
      } else {
        $("battleMobName").textContent = "Бой";
        $("mobHpBar").style.width = "0%";
        $("mobHpText").textContent = "";
        $("battleLog").innerHTML =
          "<p>Рядом нет врага. Откройте вкладку «Мир», найдите моба " +
          "на клетке и нажмите «Атаковать».</p>";
        $("attackBtn").hidden = true;
        $("fleeBtn").hidden = true;
        $("leaveBattleBtn").hidden = true;
      }
    } catch (e) { /* тихо: вкладка боя без активного боя */ }
  }

  async function startBattle() {
    try {
      var data = await api("/battle/start", "POST");
      switchTab("battle");
      renderBattle(data.state);
    } catch (e) { toast(e.message, "err"); }
  }

  async function attack() {
    try {
      var data = await api("/battle/attack", "POST");
      renderBattle(data.result);
    } catch (e) { toast(e.message, "err"); }
  }

  async function flee() {
    try {
      var data = await api("/battle/flee", "POST");
      renderBattle(data.result);
    } catch (e) { toast(e.message, "err"); }
  }

  // ── Инвентарь ────────────────────────────────────────────────────
  async function loadInventory() {
    try {
      var data = await api("/inventory");
      var inv = data.inventory;
      $("equippedList").innerHTML = inv.equipped.length
        ? inv.equipped.map(itemRow).join("") : '<div class="empty">Ничего не надето</div>';
      var bag = inv.bag.concat(inv.stash);
      $("bagList").innerHTML = bag.length
        ? bag.map(itemRow).join("") : '<div class="empty">Сумка пуста</div>';
      bindItemButtons();
    } catch (e) { toast(e.message, "err"); }
  }

  function itemRow(it) {
    var rarity = (it.rarity || "").toLowerCase();
    var action = it.equipped
      ? '<button class="btn" data-act="unequip" data-id="' + it.inventory_id + '">Снять</button>'
      : '<button class="btn primary" data-act="equip" data-id="' + it.inventory_id + '">Надеть</button>';
    return '<div class="item-row"><div class="info"><div class="name rarity-' +
      rarityClass(rarity) + '">' + esc(it.name) + (it.quantity > 1 ? " ×" + it.quantity : "") +
      '</div><div class="sub">' + esc(it.type) + " · " + esc(it.rarity) +
      (it.in_stash ? " · 🔒 карман" : "") + "</div></div>" + action + "</div>";
  }
  var RARITY_ALIASES = {
    "обычный": "common", "необычный": "uncommon", "редкий": "rare",
    "эпический": "epic", "легендарный": "legendary",
  };
  function rarityClass(r) {
    var key = String(r || "").toLowerCase();
    if (["common", "uncommon", "rare", "epic", "legendary"].indexOf(key) >= 0) return key;
    return RARITY_ALIASES[key] || "common";
  }
  function bindItemButtons() {
    document.querySelectorAll("[data-act]").forEach(function (btn) {
      btn.onclick = async function () {
        var id = parseInt(btn.dataset.id, 10);
        try {
          await api("/inventory/" + btn.dataset.act, "POST", { inventory_id: id });
          toast(btn.dataset.act === "equip" ? "Надето" : "Снято", "ok");
          loadInventory();
          loadProfile();
        } catch (e) { toast(e.message, "err"); }
      };
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ── Старт ────────────────────────────────────────────────────────
  async function enterGame() {
    $("login").hidden = true;
    $("game").hidden = false;
    switchTab("profile");
    loadCell();
  }

  function wire() {
    $("loginBtn").onclick = function () {
      var code = $("codeInput").value.trim();
      if (code.length < 4) { toast("Введи код из бота", "err"); return; }
      loginWith({ code: code }, "/auth/code");
    };
    $("codeInput").addEventListener("keydown", function (e) {
      if (e.key === "Enter") $("loginBtn").click();
    });
    document.querySelectorAll(".nav-btn").forEach(function (b) {
      b.onclick = function () { switchTab(b.dataset.tab); };
    });
    document.querySelectorAll(".dpad-btn").forEach(function (b) {
      b.onclick = function () { move(b.dataset.dir); };
    });
    $("inspectBtn").onclick = inspect;
    $("restBtn").onclick = rest;
    $("startBattleBtn").onclick = startBattle;
    $("attackBtn").onclick = attack;
    $("fleeBtn").onclick = flee;
    $("leaveBattleBtn").onclick = function () { switchTab("map"); loadCell(); };
  }

  wire();
  if (state.token) {
    enterGame();
  } else {
    tryTelegramLogin();
  }
})();
