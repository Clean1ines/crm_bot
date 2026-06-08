from __future__ import annotations

import pytest

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_env_config import (
    GroqEnvAccountSpec,
    GroqEnvConfigLoader,
)


def test_env_config_loader_resolves_available_account_keys_without_logging_values() -> (
    None
):
    config = GroqEnvConfigLoader().load(
        env={
            "GROQ_PRIMARY_API_KEY": "primary-secret",
            "GROQ_SECONDARY_API_KEY": "secondary-secret",
        },
        account_specs=(
            GroqEnvAccountSpec(
                account_ref="groq_org_primary",
                env_var_name="GROQ_PRIMARY_API_KEY",
                account_rank=0,
            ),
            GroqEnvAccountSpec(
                account_ref="groq_org_secondary",
                env_var_name="GROQ_SECONDARY_API_KEY",
                account_rank=1,
            ),
        ),
    )

    assert [account.account_seed.account_ref for account in config.accounts] == [
        "groq_org_primary",
        "groq_org_secondary",
    ]
    assert [account.account_seed.account_rank for account in config.accounts] == [0, 1]
    assert [account.api_key.value for account in config.accounts] == [
        "primary-secret",
        "secondary-secret",
    ]


def test_env_config_loader_skips_missing_keys_and_rejects_if_none_resolved() -> None:
    config = GroqEnvConfigLoader().load(
        env={
            "GROQ_PRIMARY_API_KEY": "primary-secret",
        },
        account_specs=(
            GroqEnvAccountSpec(
                account_ref="groq_org_primary",
                env_var_name="GROQ_PRIMARY_API_KEY",
                account_rank=0,
            ),
            GroqEnvAccountSpec(
                account_ref="groq_org_secondary",
                env_var_name="GROQ_SECONDARY_API_KEY",
                account_rank=1,
            ),
        ),
    )

    assert len(config.accounts) == 1
    assert config.accounts[0].account_seed.account_ref == "groq_org_primary"

    with pytest.raises(ValueError):
        GroqEnvConfigLoader().load(
            env={},
            account_specs=(
                GroqEnvAccountSpec(
                    account_ref="groq_org_primary",
                    env_var_name="GROQ_PRIMARY_API_KEY",
                    account_rank=0,
                ),
            ),
        )


def test_env_account_spec_validates_fields() -> None:
    with pytest.raises(ValueError):
        GroqEnvAccountSpec(account_ref="", env_var_name="KEY", account_rank=0)

    with pytest.raises(ValueError):
        GroqEnvAccountSpec(account_ref="account", env_var_name="", account_rank=0)

    with pytest.raises(ValueError):
        GroqEnvAccountSpec(account_ref="account", env_var_name="KEY", account_rank=-1)
