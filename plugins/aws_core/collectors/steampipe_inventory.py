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

_SITE_RUN_STARTED = "019e27be-3a6c-71c3-a443-7b79931e0ef9"
_SITE_CONFIG_INVALID = "019e27be-3a6d-7287-b2e9-dc25104be557"
_SITE_PROFILE_INVALID = "019e27be-3a6d-7287-b2e9-dc26f8156779"
_SITE_STEAMPIPE_FAILED = "019e27be-3a6d-7287-b2e9-dc27592f1be1"
_SITE_PROFILE_COLLECTED = "019e27be-3a6d-7287-b2e9-dc28a97b7a5f"
_SITE_RUN_COMPLETED = "019e27be-3a6d-7287-b2e9-dc2913127c83"


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
                context=target_config.to_context(),
            )
            raise

        try:
            result = self.runner_cls().run_profile(profile, target_config)
        except SteampipeRunnerError as exc:
            self.record_error(
                _SITE_STEAMPIPE_FAILED,
                "STEAMPIPE_FAILED",
                str(exc),
                context=target_config.to_context(),
            )
            raise

        self.profile_result = result
        self.record_info(
            _SITE_PROFILE_COLLECTED,
            "PROFILE_COLLECTED",
            f"AWS Steampipe profile {profile.key} collected successfully.",
            context={
                **target_config.to_context(),
                "tables": {
                    table: {"rows": len(rows)}
                    for table, rows in sorted(result.rows_by_table.items())
                },
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
            context={"summary": self.summary},
        )
