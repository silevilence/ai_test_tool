from __future__ import annotations

import json

from core.config import ModelConfig, ModelConfigStore


class FakeSecretCipher:
    def encrypt(self, value: str) -> str:
        return f"enc::{value[::-1]}"

    def decrypt(self, value: str) -> str:
        assert value.startswith("enc::")
        return value.removeprefix("enc::")[::-1]


def test_model_config_store_persists_encrypted_api_keys(tmp_path) -> None:
    storage_path = tmp_path / "model_configs.json"
    cipher = FakeSecretCipher()
    store = ModelConfigStore(storage_path=storage_path, secret_cipher=cipher)

    store.upsert(
        ModelConfig(
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="top-secret",
            model_name="gpt-4.1",
        )
    )

    payload = json.loads(storage_path.read_text(encoding="utf-8"))

    assert payload == {
        "configs": [
            {
                "display_name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_key": "enc::terces-pot",
                "model_name": "gpt-4.1",
            }
        ]
    }

    reloaded_store = ModelConfigStore(storage_path=storage_path, secret_cipher=cipher)

    assert reloaded_store.list_all() == [
        ModelConfig(
            display_name="OpenAI",
            base_url="https://api.openai.com/v1",
            api_key="top-secret",
            model_name="gpt-4.1",
        )
    ]


def test_model_config_store_remove_updates_persistent_storage(tmp_path) -> None:
    storage_path = tmp_path / "model_configs.json"
    cipher = FakeSecretCipher()
    store = ModelConfigStore(storage_path=storage_path, secret_cipher=cipher)

    store.upsert(
        ModelConfig(
            display_name="DeepSeek",
            base_url="https://api.deepseek.com",
            api_key="secret-key",
            model_name="deepseek-chat",
        )
    )

    store.remove("DeepSeek")

    reloaded_store = ModelConfigStore(storage_path=storage_path, secret_cipher=cipher)

    assert reloaded_store.list_all() == []