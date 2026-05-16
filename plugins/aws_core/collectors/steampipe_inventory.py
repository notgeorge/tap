"""AWS Steampipe inventory collector shell.

Spec: plugins/aws_core/specs/spec-aws-steampipe-collector-v0.md
"""

from __future__ import annotations

import logging

from plugins.aws_core.collectors.config import (
    AwsSteampipeConfigError,
    load_aws_steampipe_collector_config,
)
from plugins.aws_core.collectors.credentials import resolve_aws_static_credentials
from plugins.aws_core.collectors.profiles import AwsSteampipeProfileError, get_profile
from plugins.aws_core.collectors.steampipe_runner import (
    SteampipeProfileResult,
    SteampipeRunner,
    SteampipeRunnerError,
)
from tap_cares.collectors import CollectorBase, CollectorConfig
from tap_cares.exceptions import SecretError

logger = logging.getLogger(__name__)

# 4-hex site token per record_* callsite, minted via scripts/log-site-id.
# Unique within this file (req-tap-logging-site-ids).
_SITE_RUN_STARTED = "4bc1"
_SITE_CONFIG_INVALID = "a16d"
_SITE_PROFILE_INVALID = "3609"
_SITE_SECRET_INVALID = "5cac"
_SITE_STEAMPIPE_FAILED = "ce26"
_SITE_PROFILE_COLLECTED = "a766"
_SITE_RUN_COMPLETED = "ac11"


class AwsSteampipeInventoryCollector(CollectorBase):
    """Collector shell for trusted AWS Steampipe inventory profiles."""

    runner_cls: type[SteampipeRunner] = SteampipeRunner

    def __init__(self, config: CollectorConfig) -> None:
        super().__init__(config)
        self.profile_result: SteampipeProfileResult | None = None

    def run(self) -> None:
        self.record_info(
            _SITE_RUN_STARTED,
            "RUN_STARTED",
            "AWS Steampipe inventory collection started.",
        )
        logger.info("[2d3c] aws_steampipe_collection_started")

        try:
            target_config = load_aws_steampipe_collector_config()
        except AwsSteampipeConfigError as exc:
            self.record_error(
                _SITE_CONFIG_INVALID,
                "CONFIG_INVALID",
                str(exc),
            )
            self.summary = "AWS Steampipe collector configuration is invalid."
            logger.exception("[23ab] aws_steampipe_config_invalid")
            raise

        try:
            profile = get_profile(target_config.profile)
        except AwsSteampipeProfileError as exc:
            self.record_error(
                _SITE_PROFILE_INVALID,
                "PROFILE_INVALID",
                str(exc),
                message_data=target_config.to_context(),
            )
            self.summary = f"AWS Steampipe profile {target_config.profile!r} is invalid."
            logger.exception(
                "[efc4] aws_steampipe_profile_invalid target=%s profile=%s",
                target_config.target_key,
                target_config.profile,
            )
            raise

        try:
            credentials = resolve_aws_static_credentials(target_config.secret_ref)
        except SecretError as exc:
            self.record_error(
                _SITE_SECRET_INVALID,
                "SECRET_INVALID",
                str(exc),
                message_data=target_config.to_context(),
            )
            self.summary = (
                f"AWS Steampipe credentials for {target_config.target_key} "
                f"{profile.key} are invalid or missing."
            )
            logger.exception(
                "[d15e] aws_steampipe_secret_invalid target=%s secret_ref=%s",
                target_config.target_key,
                target_config.secret_ref.qualified,
            )
            raise

        try:
            result = self.runner_cls().run_profile(
                profile,
                target_config,
                env=credentials.as_steampipe_env(region=target_config.regions[0]),
                redaction_values=credentials.redaction_values(),
            )
        except SteampipeRunnerError as exc:
            self.record_error(
                _SITE_STEAMPIPE_FAILED,
                "STEAMPIPE_FAILED",
                str(exc),
                message_data=target_config.to_context(),
            )
            self.summary = (
                f"AWS Steampipe run failed for {target_config.target_key} "
                f"{profile.key}."
            )
            logger.exception(
                "[a8b9] aws_steampipe_runner_failed target=%s profile=%s",
                target_config.target_key,
                profile.key,
            )
            raise

        self.profile_result = result
        self.record_info(
            _SITE_PROFILE_COLLECTED,
            "PROFILE_COLLECTED",
            f"AWS Steampipe profile {profile.key} collected successfully.",
            message_data={
                **target_config.to_context(),
                "tables": {table: {"rows": len(rows)} for table, rows in sorted(result.rows_by_table.items())},
                "warnings": result.warnings,
            },
        )
        logger.info(
            "[7f31] aws_steampipe_profile_collected target=%s profile=%s tables=%s",
            target_config.target_key,
            profile.key,
            sorted(result.rows_by_table),
        )

        vpc_rows = result.row_count("aws_vpc")
        subnet_rows = result.row_count("aws_vpc_subnet")
        self.summary = (
            f"Collected AWS {target_config.target_key} {profile.key}: "
            f"{vpc_rows} VPC rows, {subnet_rows} subnet rows "
            "(normalization pending)."
        )
        self.record_info(
            _SITE_RUN_COMPLETED,
            "RUN_COMPLETED",
            "AWS Steampipe inventory collection complete.",
            message_data={"summary": self.summary},
        )
        logger.info(
            "[44d2] aws_steampipe_collection_completed target=%s profile=%s",
            target_config.target_key,
            profile.key,
        )
