"""Ключ кеша из текста и настроек синтеза."""

from micro_tts.errors import TtsError


def _fnv1a(data):
    value = 0xcbf29ce484222325
    for byte in data:
        value ^= byte
        value = (value * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return "{:016x}".format(value)


def _fnv1a_text(text):
    value = 0xcbf29ce484222325
    for char in text:
        code = ord(char)
        for shift in (0, 8, 16, 24):
            value ^= (code >> shift) & 0xFF
            value = (value * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return "{:016x}".format(value)


def _format_value(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TtsError("{} должен быть числом".format(name))
    return "{:.6f}".format(float(value))


def _format_field(fmt, name):
    if isinstance(fmt, dict):
        return fmt.get(name, 0)
    return getattr(fmt, name, 0)


def cache_key(text, engine_tag, voice, rate, pitch, normalizer, fmt):
    """Стабильный ключ кеша.

    В ключ входят текст, версия движка, голос, темп, высота, язык и
    версия нормализатора, формат PCM.
    """
    if not isinstance(text, str) or not text:
        raise TtsError("ключ кеша: пустой текст")
    if not isinstance(engine_tag, str) or not engine_tag:
        raise TtsError("ключ кеша: пустая метка движка")
    voice = "" if voice is None else str(voice)
    rate = _format_value(rate, "rate")
    pitch = _format_value(pitch, "pitch")
    language = getattr(normalizer, "language", "") if normalizer else ""
    version = getattr(normalizer, "version", "") if normalizer else ""
    rate_hz = _format_field(fmt, "rate")
    channels = _format_field(fmt, "channels")
    width = _format_field(fmt, "width")
    if (isinstance(rate_hz, bool) or not isinstance(rate_hz, int)
            or rate_hz <= 0):
        raise TtsError("ключ кеша: неверная частота")
    payload = "|".join((
        "v1",
        str(len(text)),
        text,
        engine_tag,
        voice,
        rate,
        pitch,
        str(language),
        str(version),
        str(rate_hz),
        str(channels),
        str(width),
    ))
    try:
        data = payload.encode("utf-8")
    except AttributeError:
        return _fnv1a_text(payload)
    try:
        import hashlib
        return hashlib.sha256(data).hexdigest()
    except (ImportError, AttributeError):
        return _fnv1a(data)
