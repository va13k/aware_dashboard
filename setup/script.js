var step = 0,
  ssl = false,
  redirectTimer = null,
  suggestedPublicHost = "",
  customPublicHost = "",
  hasExistingResearcherAuth = false,
  researcherCredentials = null;

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

function suggestPassword() {
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
  document.getElementById("researcherPass").value = parts.join("-");
}

function go(dir) {
  var next = step + dir;
  if (next < 0 || next > 4) return;

  if (dir > 0) {
    if (step === 0) {
      var mp = (document.getElementById("mysqlPass").value || "").trim();
      if (!mp) {
        showFieldError("mysqlPass", "Please enter a MySQL root password.");
        return;
      }
    }
    if (step === 1) {
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

function getPayload() {
  var mp = (document.getElementById("mysqlPass").value || "CHANGE_ME").trim();
  var ru = (document.getElementById("researcherUser").value || "").trim();
  var rp = (document.getElementById("researcherPass").value || "").trim();
  var host = getSelectedHost() || "localhost";
  var proto = ssl ? "https" : "http";
  var publicPort = ssl ? "443" : "80";

  return {
    mysql_root_password: mp,
    researcher_username: ru,
    researcher_password: rp,
    public_host: host || "localhost",
    public_port: publicPort,
    protocol: proto,
    ssl_certificate_path: ssl
      ? (document.getElementById("certPath").value || "").trim()
      : "",
    ssl_certificate_key_path: ssl
      ? (document.getElementById("keyPath").value || "").trim()
      : "",
  };
}

function getEnv() {
  var payload = getPayload();
  var e =
    "MYSQL_ROOT_PASSWORD=" +
    payload.mysql_root_password +
    "\n" +
    "PUBLIC_HOST=" +
    payload.public_host +
    "\n" +
    "PUBLIC_PORT=" +
    payload.public_port +
    "\n" +
    "PROTOCOL=" +
    payload.protocol;
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

function finishDeployment() {
  var baseUrl = getBaseUrl();
  var mainPageUrl = baseUrl + "/";
  document.getElementById("statusIcon").className = "status-icon success";
  document.getElementById("statusIcon").innerHTML =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#33B5E5" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  document.getElementById("statusTitle").textContent = "Deployment complete";

  if (researcherCredentials && researcherCredentials.username) {
    document.getElementById("credentialsBox").classList.remove("hidden");
    document.getElementById("credentialsText").textContent =
      "Username: " +
      researcherCredentials.username +
      "\nPassword: " +
      researcherCredentials.password;
    document.getElementById("statusDesc").textContent =
      "Services are ready. Save the credentials above, then visit the main page.";
  } else {
    document.getElementById("statusDesc").textContent =
      "Services are ready. Redirecting to the main page.";
  }
  redirectTimer = setTimeout(function () {
    window.location.href = mainPageUrl;
  }, 2500);
}

function waitForServices() {
  var attempts = 0;
  var maxAttempts = 360;
  var ALL_SERVICES = [
    "aware_mysql",
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
          finishDeployment();
          return;
        }
        document.getElementById("statusTitle").textContent =
          "Starting services…";
        if (data.socket_unavailable) {
          document.getElementById("statusDesc").textContent =
            "Docker socket not available. Services are starting—this may take a moment.";
          if (attempts >= 20) {
            finishDeployment();
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
      suggestedPublicHost = (d.SUGGESTED_PUBLIC_HOST || "").trim();
      updateHostPlaceholder();
      if (d.MYSQL_ROOT_PASSWORD)
        document.getElementById("mysqlPass").value = d.MYSQL_ROOT_PASSWORD;

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
        if (suggestedPublicHost) {
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
  };
  x.send();
}

loadExisting();
