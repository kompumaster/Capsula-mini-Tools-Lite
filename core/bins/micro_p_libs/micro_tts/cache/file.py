"""Файловый кеш с индексом и LRU.

Один процесс: индекс держится в памяти, запись атомарная.
"""

import json
import os
import time

from micro_tts.cache.base import Cache
from micro_tts.cache.codec import WavCodec
from micro_tts.errors import TtsError

_KEY_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789_-"
)


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _limit(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TtsError("{} должен быть целым неотрицательным".format(name))
    return value


class FileCache(Cache):
    """Кеш в каталоге: `index.json` и файлы записей."""

    def __init__(self, path, codec=None, codecs=None, max_bytes=0,
                 max_entries=0, max_chars=0):
        if not isinstance(path, str) or not path:
            raise TtsError("пустой путь кеша")
        self.path = path
        self.entries_dir = path + "/entries"
        self.index_path = path + "/index.json"
        if codecs is None:
            codecs = {}
            if codec is not None:
                codecs[getattr(codec, "name", "")] = codec
            else:
                default = WavCodec()
                codecs[default.name] = default
        if not isinstance(codecs, dict) or not codecs:
            raise TtsError("нужен хотя бы один кодек кеша")
        self.codecs = {}
        for _name, item in codecs.items():
            name = getattr(item, "name", None)
            if not isinstance(name, str) or not name:
                raise TtsError("у кодека нет имени")
            for char in name:
                if char not in _KEY_CHARS:
                    raise TtsError("неверное имя кодека кеша")
            self.codecs[name] = item
        self.codec = self.codecs.get("wav")
        if self.codec is None:
            self.codec = list(self.codecs.values())[0]
        self.max_bytes = _limit(max_bytes, "max_bytes")
        self.max_entries = _limit(max_entries, "max_entries")
        self.max_chars = _limit(max_chars, "max_chars")
        self._hits = 0
        self._misses = 0
        self._index = {"version": 1, "entries": {}}
        self._load_index()

    # --- индекс ----------------------------------------------------

    def _load_index(self):
        try:
            handle = open(self.index_path, "r")
            try:
                text = handle.read()
            finally:
                handle.close()
        except OSError:
            return
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return
        clean = {}
        for key, meta in entries.items():
            if isinstance(key, str) and isinstance(meta, dict):
                clean[key] = meta
        self._index = {"version": data.get("version", 1),
                       "entries": clean}

    def _save_index(self):
        try:
            self._ensure_dirs()
            path = self.index_path + ".tmp"
            handle = open(path, "w")
            try:
                handle.write(json.dumps(self._index))
            finally:
                handle.close()
            os.rename(path, self.index_path)
            return True
        except (OSError, TypeError, ValueError):
            try:
                os.remove(self.index_path + ".tmp")
            except OSError:
                pass
            return False

    def _ensure_dirs(self):
        for path in (self.path, self.entries_dir):
            if not _exists(path):
                os.mkdir(path)

    def _entry_path(self, key, name=None):
        if not isinstance(key, str) or not key:
            raise TtsError("пустой ключ кеша")
        for char in key:
            if char not in _KEY_CHARS:
                raise TtsError("неверный ключ кеша: {!r}".format(key))
        if name is None:
            name = self.codec.name
        if not isinstance(name, str) or not name:
            raise TtsError("неверное имя кодека кеша")
        for char in name:
            if char not in _KEY_CHARS:
                raise TtsError("неверное имя кодека кеша")
        return "{}/{}.{}".format(self.entries_dir, key, name)

    # --- записи ----------------------------------------------------

    def _remove(self, key):
        self._index["entries"].pop(key, None)
        try:
            path = self._entry_path(key)
        except TtsError:
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def _total_bytes(self):
        total = 0
        for meta in self._index["entries"].values():
            try:
                total += int(meta.get("size", 0))
            except (TypeError, ValueError):
                pass
        return total

    def _oldest(self):
        entries = self._index["entries"]
        oldest = None
        oldest_used = None
        for key, meta in entries.items():
            try:
                used = float(meta.get("used", meta.get("created", 0)))
            except (TypeError, ValueError):
                used = 0.0
            if oldest is None or used < oldest_used:
                oldest = key
                oldest_used = used
        return oldest

    def _evict_one(self):
        key = self._oldest()
        if key is None:
            return False
        self._remove(key)
        return True

    def _enforce_limits(self):
        entries = self._index["entries"]
        if self.max_entries > 0:
            while len(entries) > self.max_entries:
                if not self._evict_one():
                    break
        if self.max_bytes > 0:
            while self._total_bytes() > self.max_bytes:
                if not self._evict_one():
                    break

    # --- интерфейс -------------------------------------------------

    def get(self, key, text=None):
        meta = self._index["entries"].get(key)
        if not isinstance(meta, dict):
            self._misses += 1
            return None
        if text is not None and meta.get("text") != text:
            self._remove(key)
            self._save_index()
            self._misses += 1
            return None
        name = meta.get("codec")
        codec = self.codecs.get(name) if isinstance(name, str) else None
        if codec is None:
            self._remove(key)
            self._save_index()
            self._misses += 1
            return None
        try:
            path = self._entry_path(key, name)
            handle = open(path, "rb")
            try:
                data = handle.read()
            finally:
                handle.close()
            pcm, rate = codec.decode(data)
        except (OSError, TtsError):
            self._remove(key)
            self._save_index()
            self._misses += 1
            return None
        except Exception:
            self._remove(key)
            self._save_index()
            self._misses += 1
            return None
        if (not isinstance(pcm, (bytes, bytearray)) or not pcm
                or isinstance(rate, bool) or not isinstance(rate, int)
                or rate <= 0):
            self._remove(key)
            self._save_index()
            self._misses += 1
            return None
        meta["used"] = time.time()
        meta["hits"] = int(meta.get("hits", 0)) + 1
        self._save_index()
        self._hits += 1
        return bytes(pcm), rate, dict(meta)

    def put(self, key, pcm, rate, meta=None):
        if not isinstance(pcm, (bytes, bytearray)) or not pcm:
            return False
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            return False
        meta = meta if isinstance(meta, dict) else {}
        text = meta.get("text", "")
        if not isinstance(text, str):
            text = ""
        if self.max_chars > 0 and len(text) > self.max_chars:
            return False
        try:
            data = self.codec.encode(pcm, rate)
        except Exception:
            return False
        return self._write_entry(key, data, self.codec.name, rate, meta)

    def put_encoded(self, key, data, codec, rate, meta=None):
        """Сохранить уже сжатые байты без перекодирования."""
        if not isinstance(data, (bytes, bytearray)) or not data:
            return False
        if isinstance(rate, bool) or not isinstance(rate, int) or rate <= 0:
            return False
        if codec not in self.codecs:
            return False
        meta = meta if isinstance(meta, dict) else {}
        text = meta.get("text", "")
        if not isinstance(text, str):
            text = ""
        if self.max_chars > 0 and len(text) > self.max_chars:
            return False
        return self._write_entry(key, data, codec, rate, meta)

    def _write_entry(self, key, data, codec, rate, meta):
        if not isinstance(data, (bytes, bytearray)) or not data:
            return False
        data = bytes(data)
        if self.max_bytes > 0 and len(data) > self.max_bytes:
            return False
        try:
            path = self._entry_path(key, codec)
            self._ensure_dirs()
        except (OSError, TtsError):
            return False

        tmp = path + ".tmp"
        try:
            handle = open(tmp, "wb")
            try:
                handle.write(data)
            finally:
                handle.close()
            os.rename(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

        now = time.time()
        self._index["entries"][key] = {
            "text": meta.get("text", "") if isinstance(
                meta.get("text", ""), str) else "",
            "size": len(data),
            "rate": rate,
            "codec": codec,
            "created": now,
            "used": now,
            "hits": 0,
        }
        self._enforce_limits()
        self._save_index()
        return True

    def info(self):
        entries = self._index["entries"]
        return {
            "entries": len(entries),
            "bytes": self._total_bytes(),
            "hits": self._hits,
            "misses": self._misses,
            "path": self.path,
            "max_bytes": self.max_bytes,
            "max_entries": self.max_entries,
            "max_chars": self.max_chars,
        }

    def clear(self):
        try:
            names = os.listdir(self.entries_dir)
        except OSError:
            names = []
        for name in names:
            try:
                os.remove(self.entries_dir + "/" + name)
            except OSError:
                pass
        try:
            os.remove(self.index_path)
        except OSError:
            pass
        try:
            os.remove(self.index_path + ".tmp")
        except OSError:
            pass
        self._index = {"version": 1, "entries": {}}
        self._hits = 0
        self._misses = 0
        return True
