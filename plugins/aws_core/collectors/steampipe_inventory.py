"""AWS Steampipe inventory collector shell.

Spec: plugins/aws_core/specs/spec-aws-steampipe-collector-v0.md
"""

from __future__ import annotations

from plugins.aws_core.collectors.config import (
    AwsSteampipeConfigError,
    load_aws_steampipe_collector_config,
)
from plugins.aws_core.collectors.profiles import AwsSteampipeProfileError, get_profile
from plugins.aws_core.collectors.steampipe_runner import (
    SteampipeProfileResult,
    SteampipeRunner,
    SteampipeRunnerError,
)
from tap_cares.collectors import CollectorBase, CollectorConfig

# 4-hex site token per record_* callsite, minted via scripts/log-site-id.
# Unique within this file (req-tap-logging-site-ids).
_SITE_RUN_STARTED = "4bc1"
_SITE_CONFIG_INVALID = "a16d"
_SITE_PROFILE_INVALID = "3609"
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

        try:
            target_config = load_aws_steampipe_collector_config()
        except AwsSteampipeConfigError as exc:
            self.record_error(
                _SITE_CONFIG_INVALID,
                "CONFIG_INVALID",
                str(exc),
            )
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
            raise

        try:
            result = self.runner_cls().run_profile(profile, target_config)
        except SteampipeRunnerError as exc:
            self.record_error(
                _SITE_STEAMPIPE_FAILED,
                "STEAMPIPE_FAILED",
                str(exc),
                message_data=target_config.to_context(),
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
