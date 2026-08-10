(function () {
  var host = window.location.hostname || "localhost";
  var target = "http://" + host + ":9999/";
  var status = document.getElementById("status");
  var targetUrl = document.getElementById("target-url");
  var openSetup = document.getElementById("open-setup");
  var attempts = 0;

  targetUrl.textContent = target;
  openSetup.href = target;

  function checkSetup() {
    attempts += 1;
    fetch(target, { method: "GET", mode: "no-cors", cache: "no-store" })
      .then(function () {
        status.textContent = "Setup wizard is ready. Redirecting...";
        window.location.replace(target);
      })
      .catch(function () {
        if (attempts >= 20) {
          status.textContent =
            "Setup wizard is unavailable. Start it with ./setup.sh or docker compose --profile setup up -d setup-wizard, then retry.";
        } else {
          status.textContent =
            "Waiting for the setup wizard on port 9999...";
        }
        window.setTimeout(checkSetup, 1200);
      });
  }

  checkSetup();
})();
