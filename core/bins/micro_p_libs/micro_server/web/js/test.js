function show(text) {
  document.getElementById('out').textContent = text;
}

document.getElementById('btn').addEventListener('click', function () {
  fetch('/api/ping', {cache: 'no-store'})
    .then(function (response) { return response.json(); })
    .then(function (data) { show(JSON.stringify(data)); })
    .catch(function (error) { show('ошибка: ' + error); });
});
