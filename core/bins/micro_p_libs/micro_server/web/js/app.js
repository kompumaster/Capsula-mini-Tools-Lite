function esc(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function val(value) {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  return esc(value);
}

function row(label, value) {
  return '<div class="row"><span class="label">' + esc(label) +
    '</span><span class="value">' + val(value) + '</span></div>';
}

function put(id, html) {
  document.getElementById(id).innerHTML = html;
}

function showError(text) {
  var box = document.getElementById('error');
  if (!text) {
    box.hidden = true;
    box.textContent = '';
    return;
  }
  box.hidden = false;
  box.textContent = 'Ошибка: ' + text;
}

function load() {
  fetch('/api/status', {cache: 'no-store'})
    .then(function (response) { return response.json(); })
    .then(function (data) {
      var system = data.system || {};
      var network = data.network || {};
      var sound = data.sound || {};
      var versions = data.versions || {};
      var memory = data.memory || {};
      var moment = data.time || {};
      var saved = (network.saved || []).join(', ') || 'нет';
      var parts = [];
      if (system.board) { parts.push(system.board); }
      if (system.machine) { parts.push(system.machine); }
      var platform = parts.join(' ');

      put('system',
        row('хост', system.hostname) +
        row('платформа', platform) +
        row('ядро', system.release) +
        row('Python', system.python) +
        row('uptime', system.uptime) +
        row('время', moment.now));
      put('network',
        row('Wi-Fi', network.ssid) +
        row('состояние', network.state) +
        row('IP', network.ip) +
        row('сохранённые', saved) +
        row('ошибка', network.error));
      put('sound', row('громкость', sound.volume) +
        row('ошибка', sound.error));
      put('versions',
        row('micro_server', versions.micro_server) +
        row('micro_hal', versions.micro_hal) +
        row('micro_tts', versions.micro_tts) +
        row('micro_asr', versions.micro_asr));
      put('memory', row('свободно', memory.free) +
        row('занято', memory.alloc));
      showError(null);
      var updated = document.getElementById('updated');
      if (updated) {
        updated.textContent = 'обновлено ' +
          new Date().toLocaleTimeString();
      }
    })
    .catch(function (error) { showError(error); });
}

var refresh = document.getElementById('refresh');
if (refresh) {
  refresh.addEventListener('click', function (event) {
    event.preventDefault();
    load();
  });
}

document.addEventListener('visibilitychange', function () {
  if (!document.hidden) {
    load();
  }
});

load();
setInterval(function () {
  if (!document.hidden) {
    load();
  }
}, 15000);
