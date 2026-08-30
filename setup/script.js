var step = 0,
  ssl = false,
  // Encryption to a database this deployment does not run. On by default because
  // almost every server offers it, and the question is only asked for the one
  // placement whose server this deployment does not administer.
  dbTls = true,
  // What follows the study to a database this deployment does not run. Both off:
  // moving decides where the next row is written, and copying gigabytes onto
  // somebody else's server, or pulling them back every night, is a separate answer
  // from a researcher who knows what that server is for.
  dbCarryData = false,
  dbKeepBackups = false,
  redirectTimer = null,
  suggestedPublicHost = "",
  customPublicHost = "",
  hasExistingResearcherAuth = false,
  researcherCredentials = null,
  participantPassword = "",
  deploymentUrls = null;

// Characters that survive .env, the wizard's JSON responses and MySQL quoting
// unambiguously, and that a participant can retype from a printed sheet.
var PASSWORD_PATTERN = /^[A-Za-z0-9._~@#%^*+=:-]+$/;

// Password fields that carry a reveal button, each paired with a button whose
// id is the field's id + "Eye".
var PASSWORD_FIELDS = ["mysqlPass", "participantPass", "researcherPass"];

var EYE_ICON =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';

var EYE_OFF_ICON =
  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>' +
  '<line x1="1" y1="1" x2="23" y2="23"/></svg>';

function renderEyeButton(id) {
  var revealed = document.getElementById(id).type === "text";
  var button = document.getElementById(id + "Eye");
  // The icon shows the action the click performs, not the current state.
  button.innerHTML = revealed ? EYE_OFF_ICON : EYE_ICON;
  button.setAttribute("aria-pressed", revealed ? "true" : "false");
  button.setAttribute("aria-controls", id);
  var label = revealed ? "Hide password" : "Show password";
  button.setAttribute("aria-label", label);
  button.title = label;
}

function togglePasswordVisibility(id) {
  var input = document.getElementById(id);
  input.type = input.type === "password" ? "text" : "password";
  renderEyeButton(id);
  input.focus();
}

function initPasswordToggles() {
  for (var i = 0; i < PASSWORD_FIELDS.length; i++) {
    renderEyeButton(PASSWORD_FIELDS[i]);
  }
}

function getSelectedHost() {
  return (document.getElementById("publicHost").value || "").trim();
}

function updateHostPlaceholder() {
  var hostInput = document.getElementById("publicHost");
  hostInput.placeholder = suggestedPublicHost || "study.example.com";
}

function updateHostInput() {
  var mode = document.getElementById("publicHostMode").value;
  var hostInput = document.getElementById("publicHost");
  updateHostPlaceholder();

  if (mode === "localhost") {
    hostInput.value = "localhost";
    hostInput.disabled = true;
    return;
  }

  if (mode === "detected") {
    hostInput.value = suggestedPublicHost || "localhost";
    hostInput.disabled = true;
    return;
  }

  hostInput.disabled = false;
  hostInput.value = customPublicHost;
  hostInput.focus();
}

function rememberCustomHost() {
  if (document.getElementById("publicHostMode").value !== "custom") {
    return;
  }
  customPublicHost = (document.getElementById("publicHost").value || "").trim();
}

function setHostSelection(host) {
  var normalized = (host || "").trim();
  var mode = document.getElementById("publicHostMode");
  var hostInput = document.getElementById("publicHost");

  if (!normalized && suggestedPublicHost) {
    normalized = suggestedPublicHost;
  }

  if (normalized === "localhost") {
    mode.value = "localhost";
    hostInput.value = "localhost";
    hostInput.disabled = true;
    customPublicHost = "";
    return;
  }

  if (normalized && suggestedPublicHost && normalized === suggestedPublicHost) {
    mode.value = "detected";
    hostInput.value = suggestedPublicHost;
    hostInput.disabled = true;
    customPublicHost = "";
    return;
  }

  mode.value = "custom";
  customPublicHost = normalized;
  hostInput.value = customPublicHost;
  hostInput.disabled = false;
}

function showFieldError(id, msg) {
  var input = document.getElementById(id);
  var errEl = document.getElementById(id + "Error");
  input.classList.add("invalid");
  errEl.textContent = msg;
  errEl.classList.remove("hidden");
  input.focus();
}

function clearFieldError(id) {
  document.getElementById(id).classList.remove("invalid");
  document.getElementById(id + "Error").classList.add("hidden");
}

function positiveIntegerValue(id, fallback) {
  var value = Number((document.getElementById(id).value || "").trim());
  if (!Number.isFinite(value) || value < 1) {
    return fallback;
  }
  return Math.floor(value);
}

function validateBackups() {
  var backupHostDir = (
    document.getElementById("backupHostDir").value || ""
  ).trim();
  var valid = true;

  if (!backupHostDir) {
    showFieldError("backupHostDir", "Please enter a backup folder.");
    valid = false;
  } else if (/\s/.test(backupHostDir)) {
    showFieldError("backupHostDir", "Use a path without spaces.");
    valid = false;
  }

  if (positiveIntegerValue("backupIntervalDays", 0) < 1) {
    showFieldError("backupIntervalDays", "Enter at least 1 day.");
    valid = false;
  }

  if (positiveIntegerValue("backupRetentionDays", 0) < 1) {
    showFieldError("backupRetentionDays", "Enter at least 1 day.");
    valid = false;
  }

  return valid;
}

function suggestPassword(id) {
  var chars = "abcdefghjkmnpqrstuvwxyz23456789";
  var buf = new Uint8Array(16);
  crypto.getRandomValues(buf);
  var parts = [];
  for (var i = 0; i < 4; i++) {
    var part = "";
    for (var j = 0; j < 4; j++) {
      part += chars[buf[i * 4 + j] % chars.length];
    }
    parts.push(part);
  }
  document.getElementById(id || "researcherPass").value = parts.join("-");
}

function go(dir) {
  var next = step + dir;
  if (next < 0 || next > 4) return;

  if (dir > 0) {

    // A connection string pasted whole is the common mistake here: providers
    // hand out one line with the scheme, the credentials and the database in
    // it, and this field wants the host alone. Left to the deployment, it comes
    // back as a DNS failure naming the whole string -- password included.
    if (step === 1) {
      var mp = (document.getElementById("mysqlPass").value || "").trim();
      if (!mp) {
        showFieldError("mysqlPass", "Please enter the database password.");
        return;
      }
    }
    if (step === 1 && dbPlacement() === "external") {
      var host = dbHost();
      if (!host) {
        showFieldError("dbHost", "Please enter the database host.");
        return;
      }
      // A connection string is what the provider gives out, so it is taken
      // apart rather than sent back: the parts land in their own fields, where
      // they can be seen and corrected.
      if (host.indexOf("://") !== -1 && spreadConnectionString(host)) {
        host = dbHost();
      }
      if (/^[a-z][a-z0-9+.-]*:\/\//i.test(host) || host.indexOf("@") !== -1) {
        showFieldError(
          "dbHost",
          "This does not read as a host or a connection string. Enter the host on its own, such as db.example.edu, and the port in the field below.",
        );
        return;
      }
      if (host.indexOf("/") !== -1 || host.indexOf("?") !== -1) {
        showFieldError(
          "dbHost",
          "Enter the host on its own, without a path or query — the database name and options are settled by this deployment.",
        );
        return;
      }
      if (host.indexOf(":") !== -1) {
        showFieldError(
          "dbHost",
          "Leave the port out of this field; there is a separate one for it below.",
        );
        return;
      }
      if (/\s/.test(host)) {
        showFieldError("dbHost", "A host name has no spaces in it.");
        return;
      }
      clearFieldError("dbHost");
      fillAdminFromHost();
    }
    // Caught before the request so a half-copied paste is a corrected field
    // rather than a refused deployment. The server checks it again, because a
    // form is not a boundary.
    if (step === 1 && dbPlacement() === "external" && dbTls) {
      var ca = dbCaCertificate();
      if (
        ca &&
        !/-----BEGIN CERTIFICATE-----[\s\S]*-----END CERTIFICATE-----/.test(ca)
      ) {
        showFieldError(
          "dbCaCertificate",
          "Paste the whole file, from -----BEGIN CERTIFICATE----- to -----END CERTIFICATE-----.",
        );
        return;
      }
    }
    if (step === 1 && androidDataflow() === "direct") {
      var pp = (document.getElementById("participantPass").value || "").trim();
      if (pp && !PASSWORD_PATTERN.test(pp)) {
        showFieldError(
          "participantPass",
          "Use letters, digits or . _ ~ @ # % ^ * + = : - only.",
        );
        return;
      }
    }
    if (step === 0) {
      var ru = (document.getElementById("researcherUser").value || "").trim();
      var rp = (document.getElementById("researcherPass").value || "").trim();
      var valid = true;
      if (!ru) {
        showFieldError("researcherUser", "Please enter a username.");
        valid = false;
      }
      if (!rp && !hasExistingResearcherAuth) {
        showFieldError("researcherPass", "Please enter a password.");
        valid = false;
      }
      if (!valid) return;
    }
    if (step === 2 && !validateBackups()) {
      return;
    }
  }

  if (next === 3) buildPreview();
  if (next === 4) deploy();

  document.getElementById("s" + (step + 1)).classList.add("hidden");
  document.getElementById("s" + (next + 1)).classList.remove("hidden");

  var bars = document.querySelectorAll(".steps span");
  for (var i = 0; i < bars.length; i++) {
    bars[i].className = i < next ? "done" : i === next ? "active" : "";
  }
  step = next;

  var back = document.getElementById("backBtn");
  var nb = document.getElementById("nextBtn");
  var nav = document.getElementById("nav");

  nav.classList.remove("hidden");
  back.classList.toggle("hidden", step === 0);
  nb.classList.remove("hidden");

  if (step === 3) {
    nb.textContent = "Deploy";
  } else if (step === 4) {
    nav.classList.add("hidden");
  } else {
    nb.textContent = "Next";
  }
}

function restart() {
  if (redirectTimer) {
    clearTimeout(redirectTimer);
    redirectTimer = null;
  }
  document.getElementById("s5").classList.add("hidden");
  document.getElementById("s1").classList.remove("hidden");
  document.getElementById("statusIcon").className = "status-icon loading";
  document.getElementById("statusIcon").innerHTML =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#33B5E5" stroke-width="2"><path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83"/></svg>';
  document.getElementById("statusTitle").textContent = "Deploying...";
  document.getElementById("statusDesc").textContent =
    "Writing configuration and starting containers.";
  document.getElementById("errorDetail").classList.add("hidden");
  document.getElementById("editBtn").classList.add("hidden");
  document.getElementById("credentialsBox").classList.add("hidden");
  document.getElementById("participantBox").classList.add("hidden");

  var bars = document.querySelectorAll(".steps span");
  for (var i = 0; i < bars.length; i++) {
    bars[i].className = i === 0 ? "active" : "";
  }
  step = 0;

  var nav = document.getElementById("nav");
  nav.classList.remove("hidden");
  document.getElementById("backBtn").classList.add("hidden");
  document.getElementById("nextBtn").classList.remove("hidden");
  document.getElementById("nextBtn").textContent = "Next";
}

function toggleSSL() {
  ssl = !ssl;
  document.getElementById("sslToggle").classList.toggle("on", ssl);
  document.getElementById("sslFields").classList.toggle("show", ssl);
}

/**
 * Whether this study opens the database it names over TLS.
 *
 * The authority field goes with it: there is nothing to verify on a connection
 * nobody encrypts, and leaving the box on screen would invite a researcher to
 * paste a certificate that changes nothing.
 */
function toggleDbTls() {
  dbTls = !dbTls;
  document.getElementById("dbTlsToggle").classList.toggle("on", dbTls);
  document.getElementById("dbCaField").classList.toggle("hidden", !dbTls);
  document.getElementById("dbPlaintextCaution").classList.toggle("hidden", dbTls);
  if (!dbTls) clearFieldError("dbCaCertificate");
}

// The copy is offered rather than done here: a study's data is measured in
// gigabytes, and the deploy answers a browser waiting on it.
function toggleDbCarryData() {
  dbCarryData = !dbCarryData;
  document.getElementById("dbCarryDataToggle").classList.toggle("on", dbCarryData);
  updateDbMoveNotice();
}

// The backup job follows the database only if asked. It dumps the whole study
// every interval, which over a network to a server somebody else runs is a
// different arrangement from the same job inside the deployment.
function toggleDbKeepBackups() {
  dbKeepBackups = !dbKeepBackups;
  document
    .getElementById("dbKeepBackupsToggle")
    .classList.toggle("on", dbKeepBackups);
  updateDbMoveNotice();
}

// The warning states what a move leaves behind, so it belongs where nothing was
// asked for rather than next to the answers that were.
function updateDbMoveNotice() {
  var notice = document.getElementById("dbBackupAbsent");
  if (!notice) return;
  notice.classList.toggle(
    "hidden",
    dbPlacement() !== "external" || dbCarryData || dbKeepBackups,
  );
}

function dbCaCertificate() {
  var el = document.getElementById("dbCaCertificate");
  return el && el.value ? el.value.trim() : "";
}

function getPayload() {
  var mp = (document.getElementById("mysqlPass").value || "CHANGE_ME").trim();
  var ru = (document.getElementById("researcherUser").value || "").trim();
  var rp = (document.getElementById("researcherPass").value || "").trim();
  var pp = (document.getElementById("participantPass").value || "").trim();
  var host = getSelectedHost() || "localhost";
  var proto = ssl ? "https" : "http";
  var publicPort = ssl ? "443" : "80";
  var backupIntervalDays = positiveIntegerValue("backupIntervalDays", 1);
  var backupRetentionDays = positiveIntegerValue("backupRetentionDays", 30);

  return {
    mysql_root_password: mp,
    researcher_username: ru,
    researcher_password: rp,
    participant_db_password: pp,
    public_host: host || "localhost",
    public_port: publicPort,
    protocol: proto,
    android_dataflow: androidDataflow(),
    db_placement: dbPlacement(),
    db_host: dbHost(),
    db_admin_user: dbAdminUser(),
    db_init: dbInit(),
    db_port: dbPort(),
    // Sent only for the placement that has a say. A bundled database settles both
    // of these itself, and an answer arriving for it would be a form field nobody
    // was shown rather than a decision the researcher made.
    db_require_tls: dbPlacement() === "external" && !dbTls ? "0" : "1",
    db_ca_certificate:
      dbPlacement() === "external" && dbTls ? dbCaCertificate() : "",
    // Both are answers about a server this deployment does not run, so a study on
    // the bundled database sends neither: its backup job is not going anywhere and
    // there is nowhere to copy from.
    db_carry_data: dbPlacement() === "external" && dbCarryData ? "1" : "0",
    db_keep_backups: dbPlacement() === "external" && dbKeepBackups ? "1" : "0",
    mysql_backup_host_dir:
      (document.getElementById("backupHostDir").value || "").trim() ||
      "./backups/mysql",
    mysql_backup_interval_seconds: String(backupIntervalDays * 86400),
    mysql_backup_retention_days: String(backupRetentionDays),
    ssl_certificate_path: ssl
      ? (document.getElementById("certPath").value || "").trim()
      : "",
    ssl_certificate_key_path: ssl
      ? (document.getElementById("keyPath").value || "").trim()
      : "",
  };
}


// The chosen Android dataflow. A disabled option cannot be selected, so this
// reads what the researcher actually picked rather than assuming the default --
// and the server validates it again, because a form is not a boundary.
function androidDataflow() {
  var el = document.getElementById("androidDataflow");
  return (el && el.value ? el.value : "direct").trim();
}

function dbPlacement() {
  var el = document.getElementById("dbPlacement");
  return (el && el.value ? el.value : "bundled").trim();
}

function dbHost() {
  var el = document.getElementById("dbHost");
  return el && el.value ? el.value.trim() : "";
}

// What each managed service calls the account it hands out. None of them is
// root, and somebody deploying for the first time has no reason to know that, so
// the host answers it instead of a question.
var ADMIN_BY_HOST = [
  [".aivencloud.com", "avnadmin"],
  [".ondigitalocean.com", "doadmin"],
];

function adminForHost(host) {
  var name = String(host || "")
    .trim()
    .toLowerCase();
  for (var i = 0; i < ADMIN_BY_HOST.length; i += 1) {
    if (name.slice(-ADMIN_BY_HOST[i][0].length) === ADMIN_BY_HOST[i][0]) {
      return ADMIN_BY_HOST[i][1];
    }
  }
  return "";
}

// Providers hand out one line holding the host, the port, the account and the
// password. Taking it apart here means the wizard can be pasted into: whatever
// field it lands in, the parts go where they belong and the researcher sees what
// was understood.
function spreadConnectionString(text) {
  var raw = String(text || "").trim();
  if (raw.indexOf("://") === -1) return false;

  var parsed;
  try {
    parsed = new URL(raw);
  } catch (e) {
    return false;
  }
  if (!parsed.hostname) return false;

  document.getElementById("dbHost").value = parsed.hostname;
  if (parsed.port) document.getElementById("dbPort").value = parsed.port;
  if (parsed.username) {
    document.getElementById("dbAdminUser").value = decodeURIComponent(
      parsed.username,
    );
  }
  var passField = document.getElementById("mysqlPass");
  if (parsed.password && passField && !passField.value.trim()) {
    passField.value = decodeURIComponent(parsed.password);
  }
  clearFieldError("dbHost");
  return true;
}

function fillAdminFromHost() {
  var field = document.getElementById("dbAdminUser");
  if (!field || field.value.trim()) return;
  var guessed = adminForHost(dbHost());
  if (guessed) field.value = guessed;
}

// Asking before deploying, with the fields as they stand. The test creates nothing:
// it opens the database with each account this deployment uses and reports what is
// there, so a database that cannot be reached becomes a field to fix rather than a
// deploy that stops --- and what is missing before the first deploy is reported as
// the deploy's to create rather than as a failure.
function dbInit() {
  var el = document.getElementById("dbInit");
  return el && el.value === "manual" ? "manual" : "auto";
}

// Two ways for a database to become ready, and the difference is who holds the
// account that may create things. Setup can do it where the account allows;
// where it does not --- an institutional server, most often --- the file is run
// by whoever administers it and setup only checks the result.
function updateDbInit() {
  var manual = dbInit() === "manual";
  var hint = document.getElementById("dbInitHint");
  if (hint) {
    hint.textContent = manual
      ? "Download the file below and run it against the database first — it creates the schemas, this study's accounts and the tables its data lands in. The account you give setup only has to read what is there."
      : "Setup creates the schemas, this study's accounts and the tables when it deploys. It needs an account that may do that — most managed databases give you one; an institutional server often does not.";
  }
  // Offered only where it is the way the database gets made: with setup doing it,
  // the file is a thing to wonder about rather than a thing to run.
  var sqlButton = document.getElementById("dbSqlBtn");
  if (sqlButton) {
    sqlButton.className = manual ? "btn btn-next" : "btn btn-next hidden";
  }
}

function checkDatabase() {
  var button = document.getElementById("dbCheckBtn");
  var box = document.getElementById("dbCheckResult");
  if (!button || !box) return;

  spreadConnectionString(document.getElementById("dbHost").value);
  fillAdminFromHost();

  button.disabled = true;
  button.textContent = "Testing…";
  box.classList.remove("hidden");
  box.textContent = "Asking the database…";

  fetch("check-database", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      placement: dbPlacement(),
      host: dbHost(),
      port: dbPort(),
      admin_user: dbAdminUser(),
      init: dbInit(),
      admin_password: (document.getElementById("mysqlPass").value || "").trim(),
    }),
  })
    .then(function (response) {
      return response.json();
    })
    .then(function (report) {
      box.innerHTML = renderCheck(report);
    })
    .catch(function (error) {
      box.textContent = "The test could not run: " + error.message;
    })
    .finally(function () {
      button.disabled = false;
      button.textContent = "Test this database";
    });
}

function renderCheck(report) {
  var labels = {
    reachable: "Reachable",
    tls: "Encrypted",
    schema: "Schemas",
    accounts: "Study accounts",
    tables: "Tables",
  };
  var rows = (report.checks || []).map(function (entry) {
    var state = entry.skipped
      ? "skipped"
      : entry.ok
        ? "ok"
        : entry.warning
          ? "warning"
          : "failed";
    return (
      '<div class="check-row check-' +
      state +
      '"><div class="check-head">' +
      escapeHtml(labels[entry.name] || entry.name) +
      '<span class="check-state">' +
      state +
      "</span></div><div class=\"check-detail\">" +
      escapeHtml(entry.detail || "") +
      "</div></div>"
    );
  });
  var pending = (report.checks || []).some(function (entry) {
    return (
      entry.warning && ["schema", "accounts", "tables"].indexOf(entry.name) !== -1
    );
  });
  var head = !report.ok
    ? '<p class="check-verdict check-verdict-bad">Not ready yet — fix what is marked below, or run the setup file against the database.</p>'
    : pending
      ? '<p class="check-verdict check-verdict-ok">This database can take this study. What is missing is created when it deploys.</p>'
      : '<p class="check-verdict check-verdict-ok">The database is ready for this study.</p>';
  return head + rows.join("");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// The statements an administrator runs when this account may not create schemas
// or accounts, which is the usual answer at an institution.
function downloadSetupSql() {
  window.location.href = "database.sql";
}

function dbAdminUser() {
  var el = document.getElementById("dbAdminUser");
  var value = el && el.value ? el.value.trim() : "";
  // root is MySQL's own administrator and the bundled database's, so it is the
  // fallback rather than a guess.
  return value || "root";
}

function dbPort() {
  var el = document.getElementById("dbPort");
  return el && el.value ? el.value.trim() : "3306";
}

/**
 * Show the host fields for the placement that has a host, and say when the
 * placement cannot be had at all.
 *
 * An external database is offered with phones going through the server and not
 * with phones opening the database themselves, so choosing the direct dataflow
 * takes the option away rather than letting it be chosen and refused at Save.
 */
function updateDbPlacement() {
  var select = document.getElementById("dbPlacement");
  var external = document.getElementById("dbExternalFields");
  if (!select || !external) return;

  var directPath = androidDataflow() === "direct";

  external.classList.toggle("hidden", select.value !== "external");
  updateDbInit();

  // Both placements are offered on both paths. Naming a database while phones open
  // it themselves asks something of the network that an institution will usually
  // refuse — but a researcher running their own server may decide otherwise, and
  // refusing would decide it for them. The cost is stated instead.
  var caution = document.getElementById("dbExposureCaution");
  if (caution) {
    caution.classList.toggle(
      "hidden",
      !(directPath && select.value === "external"),
    );
  }

  // Asked where the placement is chosen rather than left to be discovered: what a
  // move carries over is a decision, and a deployment that made it silently would
  // either copy gigabytes nobody asked for or drop copies nobody knew were gone.
  var moving = document.getElementById("dbMoveFields");
  if (moving) {
    moving.classList.toggle("hidden", select.value !== "external");
  }
  updateDbMoveNotice();

  // A phone opens the database itself only on the direct path. On the webservice
  // path it is given a study URL and no credential, so the field is not merely
  // hidden -- the page says why there is nothing to ask for.
  document
    .getElementById("participantPassField")
    .classList.toggle("hidden", !directPath);
  document
    .getElementById("participantPassAbsent")
    .classList.toggle("hidden", directPath);
}

function getEnv() {
  var payload = getPayload();
  var e =
    "DB_ADMIN_PASSWORD=" +
    payload.mysql_root_password +
    "\n" +
    (payload.participant_db_password
      ? "PARTICIPANT_DB_PASSWORD=" + payload.participant_db_password + "\n"
      : "") +
    "PUBLIC_HOST=" +
    payload.public_host +
    "\n" +
    "PUBLIC_PORT=" +
    payload.public_port +
    "\n" +
    "PROTOCOL=" +
    payload.protocol +
    "\n" +
    "ANDROID_DATAFLOW=" +
    payload.android_dataflow +
    "\n" +
    "DB_PLACEMENT=" +
    payload.db_placement +
    "\n" +
    "DB_HOST=" +
    payload.db_host +
    "\n" +
    "DB_ADMIN_USER=" +
    payload.db_admin_user +
    "\n" +
    "DB_INIT=" +
    payload.db_init +
    "\n" +
    "DB_PORT=" +
    payload.db_port +
    "\n" +
    "DB_REQUIRE_TLS=" +
    payload.db_require_tls +
    "\n" +
    "DB_KEEP_BACKUPS=" +
    payload.db_keep_backups +
    "\n" +
    "MYSQL_BACKUP_HOST_DIR=" +
    payload.mysql_backup_host_dir +
    "\n" +
    "MYSQL_BACKUP_INTERVAL_SECONDS=" +
    payload.mysql_backup_interval_seconds +
    "\n" +
    "MYSQL_BACKUP_RETENTION_DAYS=" +
    payload.mysql_backup_retention_days;
  if (payload.protocol === "https") {
    e += "\nSSL_CERTIFICATE_PATH=" + payload.ssl_certificate_path;
    e += "\nSSL_CERTIFICATE_KEY_PATH=" + payload.ssl_certificate_key_path;
  }
  return e;
}

function buildPreview() {
  document.getElementById("envPreview").textContent = getEnv();
}

function formatHostForUrl(host) {
  var value = (host || "").trim();
  if (!value) {
    return "localhost";
  }
  if (value.startsWith("[") && value.endsWith("]")) {
    return value;
  }
  if (value.indexOf(":") !== -1) {
    return "[" + value + "]";
  }
  return value;
}

function getBaseUrl() {
  var host = getSelectedHost() || "localhost";
  var proto = ssl ? "https" : "http";
  var port = ssl ? "443" : "80";
  var isDefaultPort =
    (proto === "http" && port === "80") ||
    (proto === "https" && port === "443");
  return (
    proto + "://" + formatHostForUrl(host) + (isDefaultPort ? "" : ":" + port)
  );
}

function getReachabilityBaseUrl() {
  var currentHost = window.location.hostname || "localhost";
  var proto = ssl ? "https" : "http";
  var port = ssl ? "443" : "80";
  var isDefaultPort =
    (proto === "http" && port === "80") ||
    (proto === "https" && port === "443");
  return (
    proto +
    "://" +
    formatHostForUrl(currentHost) +
    (isDefaultPort ? "" : ":" + port)
  );
}

var CHECK_LABELS = {
  endpoint: "Endpoint reachable",
  certificate: "Certificate",
  record: "Test record lands",
  cleanup: "Probe removed",
};

/**
 * What the deployment answered when it was asked what a phone will ask.
 *
 * Drawn whether it passed or failed, because a failure here is the thing worth
 * seeing: the stack is up and healthy either way, and a study whose ingest path
 * does not work looks exactly like one that does until the data fails to arrive.
 */
function renderIngestResult(result) {
  if (!result) return;
  var box = document.getElementById("ingestBox");
  var rows = document.getElementById("ingestChecks");
  var checks = result.checks || [];

  document.getElementById("ingestTitle").textContent =
    "Ingest self-test — " + (result.dataflow || "") + " dataflow";

  rows.innerHTML = "";
  checks.forEach(function (entry) {
    var state = entry.skipped ? "skip" : entry.ok ? "ok" : "fail";
    var row = document.createElement("div");
    row.className = "check-row " + state;

    var mark = document.createElement("span");
    mark.className = "check-mark";
    mark.textContent = state === "skip" ? "skip" : state === "ok" ? "ok" : "FAIL";

    var detail = document.createElement("span");
    detail.className = "check-detail";
    var label = document.createElement("strong");
    label.textContent = (CHECK_LABELS[entry.name] || entry.name) + ": ";
    detail.appendChild(label);
    detail.appendChild(document.createTextNode(entry.detail || ""));

    row.appendChild(mark);
    row.appendChild(detail);
    rows.appendChild(row);
  });

  document.getElementById("ingestHint").textContent = result.ok
    ? "The ingest path works from outside the deployment. Enrolment can begin."
    : "Phones enrolled now would collect data and never deliver it. Fix the " +
      "failures above, then rerun: python3 setup/verify_ingest.py";
  box.classList.remove("hidden");
}

function finishDeployment(ingestResult) {
  var baseUrl = getBaseUrl();
  var urls = deploymentUrls || {};
  var mainPageUrl = urls.app_url || baseUrl + "/";
  document.getElementById("statusIcon").className = "status-icon success";
  document.getElementById("statusIcon").innerHTML =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#33B5E5" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  document.getElementById("statusTitle").textContent = "Deployment complete";

  if (participantPassword && androidDataflow() === "direct") {
    document.getElementById("participantBox").classList.remove("hidden");
    document.getElementById("participantText").textContent = participantPassword;
  }

  if (researcherCredentials && researcherCredentials.username) {
    document.getElementById("credentialsBox").classList.remove("hidden");
    document.getElementById("credentialsText").textContent =
      "Username: " +
      researcherCredentials.username +
      "\nPassword: " +
      researcherCredentials.password;
    document.getElementById("statusDesc").textContent =
      "Services are ready. Save the credentials above. Redirecting to the main page.";
  } else {
    document.getElementById("statusDesc").textContent =
      "Services are ready. Redirecting to the main page.";
  }
  renderIngestResult(ingestResult);

  // The copy is the researcher's to run, so the command is put on the page rather
  // than only in the terminal the deploy printed to.
  var carrying = dbCarryData && dbPlacement() === "external";
  if (carrying) {
    document.getElementById("dataCopyBox").classList.remove("hidden");
  }

  if (ingestResult && !ingestResult.ok) {
    document.getElementById("statusDesc").textContent =
      "Services are ready, and the ingest self-test did not pass. Read it below " +
      "before enrolling anyone.";
    document.getElementById("nav").classList.remove("hidden");
    document.getElementById("editBtn").classList.remove("hidden");
    return;
  }

  // Held here rather than redirected past: what the page is showing is a command
  // nobody has run yet.
  if (carrying) {
    document.getElementById("statusDesc").textContent =
      "Everything is running and the study is collecting into the new database. " +
      "Your earlier data has not been copied yet — the command below does that.";
    document.getElementById("nav").classList.remove("hidden");
    document.getElementById("editBtn").classList.remove("hidden");
    return;
  }

  redirectTimer = setTimeout(function () {
    window.location.href = mainPageUrl;
  }, 2500);
}

function waitForServices() {
  var attempts = 0;
  var maxAttempts = 360;
  // The self-test runs on the host once the containers report healthy, so the
  // page is ready before its answer is. Waiting a bounded while for it keeps the
  // result on screen instead of behind a redirect; giving up carries on, since a
  // deploy that never reports one is still a deploy.
  var ingestWaited = 0;
  var maxIngestWaits = 40;
  var ALL_SERVICES = [
    "aware_mysql",
    "aware_mysql_backup",
    "aware_micro",
    "aware_configurator",
    "aware_dashboard_api",
    "aware_dashboard",
    "aware_nginx",
  ];

  function labelFor(name) {
    return name.replace(/^aware_/, "");
  }

  function pollStatus() {
    fetch("status", { cache: "no-store" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        attempts += 1;
        if (data.ready) {
          if (data.ingest || ingestWaited >= maxIngestWaits) {
            finishDeployment(data.ingest || null);
            return;
          }
          ingestWaited += 1;
          document.getElementById("statusTitle").textContent =
            "Checking the ingest path…";
          document.getElementById("statusDesc").textContent =
            "Asking the deployment what a participant's phone will ask: the " +
            "endpoint at its public address, its certificate, and whether a test " +
            "record lands.";
          window.setTimeout(pollStatus, 1500);
          return;
        }
        document.getElementById("statusTitle").textContent =
          "Starting services…";
        if (data.socket_unavailable) {
          document.getElementById("statusDesc").textContent =
            "Docker socket not available. Services are starting—this may take a moment.";
          if (attempts >= 20) {
            finishDeployment(data.ingest || null);
            return;
          }
        } else {
          var svcs = data.services || {};
          var notReady = ALL_SERVICES.filter(function (n) {
            return !(n in svcs) || !svcs[n];
          }).map(labelFor);
          document.getElementById("statusDesc").textContent = notReady.length
            ? "Waiting for: " + notReady.join(", ")
            : "All containers starting…";
        }
        if (attempts >= maxAttempts) {
          showError(
            "Services did not become healthy after 3 minutes. " +
              "Run 'docker compose ps' to check container status.",
          );
          return;
        }
        window.setTimeout(pollStatus, 1500);
      })
      .catch(function () {
        attempts += 1;
        if (attempts >= maxAttempts) {
          showError("Lost contact with setup wizard.");
          return;
        }
        window.setTimeout(pollStatus, 1500);
      });
  }

  pollStatus();
}

function deploy() {
  var x = new XMLHttpRequest();
  x.open("POST", "cgi-bin/deploy", true);
  x.setRequestHeader("Content-Type", "application/json");
  x.onload = function () {
    try {
      var d = JSON.parse(x.responseText);
      if (d.success) {
        researcherCredentials = {
          username: d.researcher_username || "",
          password: d.researcher_password || "",
        };
        participantPassword = d.participant_db_password || "";
        deploymentUrls = d.urls || null;
        document.getElementById("statusTitle").textContent =
          "Starting services...";
        document.getElementById("statusDesc").textContent =
          "Configuration saved. Waiting for the deployed services.";
        waitForServices();
      } else {
        showError(d.error || "Unknown error");
      }
    } catch (e) {
      showError("Invalid response from server");
    }
  };
  x.onerror = function () {
    showError("Could not reach the setup server. Is it still running?");
  };
  var payload = getPayload();
  payload.env = getEnv();
  x.send(JSON.stringify(payload));
}

function showError(msg) {
  document.getElementById("statusIcon").className = "status-icon error";
  document.getElementById("statusIcon").innerHTML =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#E24B4A" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  document.getElementById("statusTitle").textContent = "Deployment failed";
  document.getElementById("statusDesc").textContent = "Check the error below.";
  var el = document.getElementById("errorDetail");
  el.textContent = msg;
  el.classList.remove("hidden");
  document.getElementById("nav").classList.remove("hidden");
  document.getElementById("editBtn").classList.remove("hidden");
  document.getElementById("nextBtn").classList.add("hidden");
}

function loadExisting() {
  var x = new XMLHttpRequest();
  x.open("GET", "cgi-bin/deploy", true);
  x.onload = function () {
    try {
      var d = JSON.parse(x.responseText);
      // The dataflow the study is running, so reopening the wizard on a
      // deployed study shows its own answer. Changing it forces every
      // participant to re-join, which is not something a redeploy should do
      // because a form opened on its default value.
      var deployedDataflow = (d.ANDROID_DATAFLOW || "").trim();
      var dataflowSelect = document.getElementById("androidDataflow");
      if (dataflowSelect && deployedDataflow) {
        dataflowSelect.value = deployedDataflow;
      }

      var placementSelect = document.getElementById("dbPlacement");
      if (placementSelect && (d.DB_PLACEMENT || "").trim()) {
        placementSelect.value = (d.DB_PLACEMENT || "").trim();
      }
      if ((d.DB_HOST || "").trim() && d.DB_HOST !== "db.internal") {
        document.getElementById("dbHost").value = d.DB_HOST;
      }
      if ((d.DB_PORT || "").trim()) {
        document.getElementById("dbPort").value = d.DB_PORT;
      }
      // A study that turned encryption off did so for a server that cannot offer
      // it, and that server does not change because the wizard was reopened.
      if (["0", "false", "no", "off"].indexOf((d.DB_REQUIRE_TLS || "").trim()) !== -1) {
        toggleDbTls();
      }
      // A deployment already taking copies of the server it named goes on taking
      // them: a redeploy that silently stopped would leave a study without backups
      // because a form opened on its default. The copy has no counterpart here --
      // it is done once, so reopening the wizard offers it rather than repeating it.
      if (["1", "true", "yes", "on"].indexOf((d.DB_KEEP_BACKUPS || "").trim()) !== -1) {
        toggleDbKeepBackups();
      }
      updateDbPlacement();

      suggestedPublicHost = (d.SUGGESTED_PUBLIC_HOST || "").trim();
      updateHostPlaceholder();
      // The administrator of the database this study names, whichever server that
      // is. The bundled container's own root password is never shown: it is not a
      // question anyone answers, and writing the form back would overwrite it.
      if (d.DB_ADMIN_PASSWORD)
        document.getElementById("mysqlPass").value = d.DB_ADMIN_PASSWORD;
      if ((d.DB_ADMIN_USER || "").trim())
        document.getElementById("dbAdminUser").value = d.DB_ADMIN_USER;
      if (d.PARTICIPANT_DB_PASSWORD) {
        document.getElementById("participantPass").value =
          d.PARTICIPANT_DB_PASSWORD;
        document.getElementById("participantHint").textContent =
          "Devices use this account to send data. Editing it here changes the " +
          "MySQL account on the next deployment.";
      } else {
        suggestPassword("participantPass");
      }
      document.getElementById("backupHostDir").value =
        d.MYSQL_BACKUP_HOST_DIR || "./backups/mysql";
      document.getElementById("backupIntervalDays").value = String(
        Math.max(
          1,
          Math.floor(
            Number(d.MYSQL_BACKUP_INTERVAL_SECONDS || "86400") / 86400,
          ),
        ),
      );
      document.getElementById("backupRetentionDays").value =
        d.MYSQL_BACKUP_RETENTION_DAYS || "30";

      if (d.RESEARCHER_USERNAME) {
        document.getElementById("researcherUser").value = d.RESEARCHER_USERNAME;
        hasExistingResearcherAuth = true;
        document.getElementById("researcherHint").textContent =
          "Leave blank to keep the current password";
      } else {
        document.getElementById("researcherUser").value = "researcher";
        suggestPassword();
      }

      if (d.exists) {
        setHostSelection(
          (d.PUBLIC_HOST || "").trim() || suggestedPublicHost || "localhost",
        );
      } else {
        var hostMode = document.getElementById("publicHostMode");
        var hostInput = document.getElementById("publicHost");
        var detectedLanIp = suggestedPublicHost && suggestedPublicHost !== "localhost";
        if (detectedLanIp) {
          hostMode.value = "detected";
          hostInput.value = suggestedPublicHost;
          hostInput.disabled = true;
        } else {
          hostMode.value = "localhost";
          hostInput.value = "localhost";
          hostInput.disabled = true;
        }
      }

      if (d.PROTOCOL === "https") {
        ssl = true;
        document.getElementById("sslToggle").classList.add("on");
        document.getElementById("sslFields").classList.add("show");
        document.getElementById("certPath").value =
          d.SSL_CERTIFICATE_PATH || "";
        document.getElementById("keyPath").value =
          d.SSL_CERTIFICATE_KEY_PATH || "";
      } else {
        ssl = false;
        document.getElementById("sslToggle").classList.remove("on");
        document.getElementById("sslFields").classList.remove("show");
      }
      buildPreview();
    } catch (e) {
      updateHostInput();
    }
  };
  x.onerror = function () {
    updateHostInput();
    updateDbPlacement();
  };
  x.send();
}

initPasswordToggles();
// Run once before anything is loaded, so the form opens in a state that matches
// its own default rather than showing neither the field nor the note explaining
// its absence. loadExisting() runs it again once the deployment has answered.
updateDbPlacement();
loadExisting();
