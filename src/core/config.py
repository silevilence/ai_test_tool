from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol


if os.name == "nt":
    import ctypes
    from ctypes import POINTER, Structure, byref, c_byte, c_void_p, cast
    from ctypes import wintypes

    class _DataBlob(Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(c_byte))]


    _crypt_protect_data = ctypes.windll.crypt32.CryptProtectData
    _crypt_protect_data.argtypes = [
        POINTER(_DataBlob),
        wintypes.LPCWSTR,
        POINTER(_DataBlob),
        c_void_p,
        c_void_p,
        wintypes.DWORD,
        POINTER(_DataBlob),
    ]
    _crypt_protect_data.restype = wintypes.BOOL

    _crypt_unprotect_data = ctypes.windll.crypt32.CryptUnprotectData
    _crypt_unprotect_data.argtypes = [
        POINTER(_DataBlob),
        POINTER(wintypes.LPWSTR),
        POINTER(_DataBlob),
        c_void_p,
        c_void_p,
        wintypes.DWORD,
        POINTER(_DataBlob),
    ]
    _crypt_unprotect_data.restype = wintypes.BOOL

    _local_free = ctypes.windll.kernel32.LocalFree
    _local_free.argtypes = [c_void_p]
    _local_free.restype = c_void_p


class SecretCipher(Protocol):
    def encrypt(self, value: str) -> str:
        ...

    def decrypt(self, value: str) -> str:
        ...


class PlaintextSecretCipher:
    def encrypt(self, value: str) -> str:
        return value

    def decrypt(self, value: str) -> str:
        return value


if os.name == "nt":

    def _bytes_to_blob(data: bytes) -> tuple[_DataBlob, object]:
        if not data:
            buffer = (c_byte * 1)()
            return _DataBlob(0, cast(buffer, POINTER(c_byte))), buffer

        buffer = (c_byte * len(data)).from_buffer_copy(data)
        return _DataBlob(len(data), cast(buffer, POINTER(c_byte))), buffer


    def _blob_to_bytes(blob: _DataBlob) -> bytes:
        return ctypes.string_at(blob.pbData, blob.cbData)


    class WindowsSecretCipher:
        def encrypt(self, value: str) -> str:
            payload = value.encode("utf-8")
            input_blob, _buffer = _bytes_to_blob(payload)
            output_blob = _DataBlob()

            if not _crypt_protect_data(
                byref(input_blob),
                None,
                None,
                None,
                None,
                0,
                byref(output_blob),
            ):
                raise OSError("Failed to protect model API key")

            try:
                return base64.b64encode(_blob_to_bytes(output_blob)).decode("ascii")
            finally:
                _local_free(cast(output_blob.pbData, c_void_p))

        def decrypt(self, value: str) -> str:
            encrypted_payload = base64.b64decode(value.encode("ascii"))
            input_blob, _buffer = _bytes_to_blob(encrypted_payload)
            description = wintypes.LPWSTR()
            output_blob = _DataBlob()

            if not _crypt_unprotect_data(
                byref(input_blob),
                byref(description),
                None,
                None,
                None,
                0,
                byref(output_blob),
            ):
                raise OSError("Failed to unprotect model API key")

            try:
                return _blob_to_bytes(output_blob).decode("utf-8")
            finally:
                if description:
                    _local_free(cast(description, c_void_p))
                _local_free(cast(output_blob.pbData, c_void_p))


def _build_default_secret_cipher() -> SecretCipher:
    if os.name == "nt":
        return WindowsSecretCipher()

    return PlaintextSecretCipher()


@dataclass(slots=True)
class ModelConfig:
    display_name: str
    base_url: str
    api_key: str
    model_name: str


class ModelConfigStore:
    def __init__(
        self,
        storage_path: Path | None = None,
        secret_cipher: SecretCipher | None = None,
    ) -> None:
        self._configs: dict[str, ModelConfig] = {}
        self._lock = Lock()
        self._storage_path = storage_path
        self._secret_cipher = secret_cipher or _build_default_secret_cipher()
        self._load_from_disk()

    def upsert(self, config: ModelConfig) -> None:
        with self._lock:
            self._configs[config.display_name] = config
            self._save_to_disk_locked()

    def remove(self, display_name: str) -> None:
        with self._lock:
            self._configs.pop(display_name, None)
            self._save_to_disk_locked()

    def get(self, display_name: str) -> ModelConfig | None:
        with self._lock:
            return self._configs.get(display_name)

    def list_all(self) -> list[ModelConfig]:
        with self._lock:
            return sorted(self._configs.values(), key=lambda item: item.display_name.lower())

    def _load_from_disk(self) -> None:
        if self._storage_path is None or not self._storage_path.exists():
            return

        payload = json.loads(self._storage_path.read_text(encoding="utf-8"))

        for item in payload.get("configs", []):
            config = ModelConfig(
                display_name=item["display_name"],
                base_url=item["base_url"],
                api_key=self._secret_cipher.decrypt(item["api_key"]),
                model_name=item["model_name"],
            )
            self._configs[config.display_name] = config

    def _save_to_disk_locked(self) -> None:
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "configs": [
                {
                    "display_name": config.display_name,
                    "base_url": config.base_url,
                    "api_key": self._secret_cipher.encrypt(config.api_key),
                    "model_name": config.model_name,
                }
                for config in sorted(
                    self._configs.values(),
                    key=lambda item: item.display_name.lower(),
                )
            ]
        }
        self._storage_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )