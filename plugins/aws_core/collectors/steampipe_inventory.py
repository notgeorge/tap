"""AWS Steampipe inventory collector shell.

Spec: plugins/aws_core/specs/spec-aws-steampipe-collector-v0.md

Zero-config: the collector resolves a single well-known secret and reads
credentials + region + account from it (`req-aws-steampipe-secret-discovery`).
The self-test is run phase 1 — synchronous, bounded, four accumulated checks
(`req-aws-steampipe-self-test`).
"""

from __future__ import annotations

import logging

from plugins.aws_core.collectors.config import (
    AWS_COLLECTION_SCOPE,
    AWS_STEAMPIPE_SECRET_REF,
    AwsCollectionTarget,
    AwsSteampipeConfigError,
    resolve_aws_collection_target,
)
from plugins.aws_core.collectors.profiles import AWS_CALLER_IDENTITY_QUERY, VPC_SUBNET_V0
from plugins.aws_core.collectors.steampipe_runner import (
    SteampipeProfileResult,
    SteampipeRunner,
    SteampipeRunnerError,
)
from tap_cares.collectors import (
    CollectorBase,
    CollectorConfig,
    CollectorDocRef,
    CollectorReadinessStatus,
    CollectorSelfTestCheck,
    CollectorSelfTestResult,
    check_fail,
    check_pass,
    check_skip,
)
from tap_cares.exceptions import SecretError, SecretNotFoundError
from tap_cares.secrets import resolve_secret
from tap_cares.secrets.loader import SECRET_SUFFIX

logger = logging.getLogger(__name__)

# record_* site tokens — one distinct 4-hex per callsite (req-tap-logging-site-ids).
_SITE_RUN_STARTED = "4bc1"
_SITE_TARGET_INVALID = "90af"
_SITE_SECRET_MISSING = "e252"
_SITE_SECRET_INVALID = "5cac"
_SITE_STEAMPIPE_FAILED = "ce26"
_SITE_COLLECTED = "51b5"
_SITE_RUN_COMPLETED = "ac11"


_DOC_SECRET = CollectorDocRef(
    plugin="aws_core",
    doc="setup-steampipe-collector",
    section="secret-file",
    label="Create the AWS Core secret file",
)
_DOC_STEAMPIPE = CollectorDocRef(
    plugin="aws_core",
    doc="setup-steampipe-collector",
    section="host-prerequisites",
    label="Install Steampipe prerequisites",
)
_DOC_AWS_PERMISSIONS = CollectorDocRef(
    plugin="aws_core",
    doc="setup-steampipe-collector",
    section="aws-permissions",
    label="Check AWS credentials and permissions",
)


def _aws_self_test_summary(checks: list[CollectorSelfTestCheck]) -> str:
    failures = [check for check in checks if check.is_failure]
    if not failures:
        if any(check.is_skip or check.is_warning for check in checks):
            return "AWS Steampipe collector is runnable, with self-test notes."
        return "AWS Steampipe collector is ready."
    if any(check.readiness_status == CollectorReadinessStatus.UNCONFIGURED for check in failures):
        return "AWS Steampipe collector is not configured yet (no secret)."
    if any(check.readiness_status == CollectorReadinessStatus.MISCONFIGURED for check in failures):
        return "AWS Steampipe collector configuration needs attention."
    return "AWS Steampipe collector self-test failed."


class AwsSteampipeInventoryCollector(CollectorBase):
    """Collector shell for the trusted hardcoded AWS Steampipe query set."""

    runner_cls: type[SteampipeRunner] = SteampipeRunner

    # Per-collector self-test budget override (req-tap-cares-collector-self-test-12).
    # Justification: a one-shot `steampipe query` cold-starts Steampipe's
    # embedded Postgres/FDW service every invocation, which cannot fit the 5s
    # default. Controlled slowness, not hackiness — bounded, still records an
    # explicit non-pass on timeout. Matches the run-path runner default (120s).
    SELF_TEST_LIVE_CHECK_TIMEOUT_SECONDS = 120
    SELF_TEST_AGGREGATE_DEADLINE_SECONDS = 180

    def __init__(self, config: CollectorConfig) -> None:
        super().__init__(config)
        self.profile_result: SteampipeProfileResult | None = None

    # -- Self-test (run phase 1) --------------------------------------------

    @classmethod
    def _aws_identity_check(cls, target: AwsCollectionTarget) -> CollectorSelfTestCheck:
        runner = cls.runner_cls(timeout_seconds=cls.SELF_TEST_LIVE_CHECK_TIMEOUT_SECONDS)
        try:
            result = runner.run_query(
                AWS_CALLER_IDENTITY_QUERY,
                region=target.primary_region,
                env=target.credentials.as_steampipe_env(region=target.primary_region),
                redaction_values=target.credentials.redaction_values(),
            )
        except SteampipeRunnerError as exc:
            return check_fail(
                "AWS_IDENTITY",
                f"AWS identity check failed: {type(exc).__name__}: {exc}",
                readiness_status=CollectorReadinessStatus.ERROR,
                context={"expected_account_id": target.account_id},
                docs=(_DOC_AWS_PERMISSIONS,),
            )

        row = result.rows[0] if result.rows else {}
        account = str(row.get("account_id") or "")
        arn = str(row.get("arn") or "")
        context = {
            "identity_account_id": account,
            "identity_arn_prefix": arn.split("/", 1)[0] if arn else "",
            "expected_account_id": target.account_id,
        }
        if not account:
            return check_fail(
                "AWS_IDENTITY",
                "Steampipe aws_caller_identity returned no account.",
                readiness_status=CollectorReadinessStatus.ERROR,
                context=context,
                docs=(_DOC_AWS_PERMISSIONS,),
            )
        if account != target.account_id:
            return check_fail(
                "AWS_IDENTITY",
                (
                    f"Credentials resolve to AWS account {account!r}, but the "
                    f"secret's metadata.account_id is {target.account_id!r}."
                ),
                readiness_status=CollectorReadinessStatus.MISCONFIGURED,
                context=context,
                docs=(_DOC_AWS_PERMISSIONS,),
            )
        return check_pass(
            "AWS_IDENTITY",
            f"AWS identity verified for account {account}.",
            context=context,
            docs=(_DOC_AWS_PERMISSIONS,),
        )

    @classmethod
    def self_test(cls) -> CollectorSelfTestResult:
        checks: list[CollectorSelfTestCheck] = []
        target: AwsCollectionTarget | None = None

        # 1. AWS_SECRET_PRESENT
        try:
            resolve_secret(AWS_STEAMPIPE_SECRET_REF)
        except SecretNotFoundError:
            checks.append(
                check_fail(
                    "AWS_SECRET_PRESENT",
                    (
                        f"No secret loaded for {AWS_STEAMPIPE_SECRET_REF.qualified!r}. "
                        f"Create {AWS_STEAMPIPE_SECRET_REF.key}{SECRET_SUFFIX} under "
                        "TAP_SECRETS_ROOT and restart the web container."
                    ),
                    readiness_status=CollectorReadinessStatus.UNCONFIGURED,
                    docs=(_DOC_SECRET,),
                )
            )
            secret_present = False
        else:
            checks.append(
                check_pass(
                    "AWS_SECRET_PRESENT",
                    f"Secret {AWS_STEAMPIPE_SECRET_REF.qualified!r} is loaded.",
                    docs=(_DOC_SECRET,),
                )
            )
            secret_present = True

        # 2. SECRET_VALID
        if not secret_present:
            checks.append(
                check_skip(
                    "SECRET_VALID",
                    "Skipped: no secret to validate.",
                    docs=(_DOC_SECRET,),
                )
            )
        else:
            try:
                target = resolve_aws_collection_target()
            except (SecretError, AwsSteampipeConfigError) as exc:
                checks.append(
                    check_fail(
                        "SECRET_VALID",
                        str(exc),
                        readiness_status=CollectorReadinessStatus.MISCONFIGURED,
                        docs=(_DOC_SECRET,),
                    )
                )
            else:
                checks.append(
                    check_pass(
                        "SECRET_VALID",
                        (
                            "Secret is a valid AWS credential with required "
                            f"region/account (account {target.account_id})."
                        ),
                        context=target.to_context(),
                        docs=(_DOC_SECRET,),
                    )
                )

        # 3. STEAMPIPE_AVAILABLE — plugin-owned tool (req-aws-steampipe-tooling).
        # Pure check: resolve from the plugin, never PATH; never provision.
        from plugins.aws_core.tooling import resolver

        plat_ok, plat_expected, plat_actual = resolver.platform_check()
        steampipe_ready = False
        if not plat_ok:
            checks.append(
                check_fail(
                    "STEAMPIPE_AVAILABLE",
                    (
                        f"Platform mismatch: aws_core pins [{plat_expected}] but the running "
                        f"platform is {plat_actual!r}. Multi-arch is a recorded seam; refusing "
                        f"to claim a wrong-arch tool."
                    ),
                    readiness_status=CollectorReadinessStatus.ERROR,
                    docs=(_DOC_STEAMPIPE,),
                )
            )
        elif resolver.is_provisioned():
            state = resolver.read_state() or {}
            steampipe_ready = True
            checks.append(
                check_pass(
                    "STEAMPIPE_AVAILABLE",
                    (
                        f"Plugin-owned Steampipe {state.get('steampipe_version')} present "
                        f"(aws plugin {state.get('aws_plugin_version')})."
                    ),
                    context={"binary": str(resolver.BIN_PATH), **state},
                    docs=(_DOC_STEAMPIPE,),
                )
            )
        else:
            checks.append(
                check_fail(
                    "STEAMPIPE_AVAILABLE",
                    (
                        "Steampipe is not provisioned for aws_core. Run "
                        "`manage.py plugin_standup aws_core` (or `manage.py aws_core_standup`) "
                        "to acquire it."
                    ),
                    readiness_status=CollectorReadinessStatus.ERROR,
                    docs=(_DOC_STEAMPIPE,),
                )
            )

        # 4. AWS_IDENTITY (needs a valid secret AND steampipe)
        if target is None or not steampipe_ready:
            checks.append(
                check_skip(
                    "AWS_IDENTITY",
                    "Skipped: requires a valid secret and an available Steampipe.",
                    docs=(_DOC_AWS_PERMISSIONS,),
                )
            )
        else:
            checks.append(cls._aws_identity_check(target))

        return CollectorSelfTestResult.from_checks(
            checks,
            summary=_aws_self_test_summary(checks),
            docs=(_DOC_SECRET, _DOC_STEAMPIPE, _DOC_AWS_PERMISSIONS),
        )

    # -- Run ----------------------------------------------------------------

    def run(self) -> None:
        self.record_info(
            _SITE_RUN_STARTED,
            "RUN_STARTED",
            "AWS Steampipe inventory collection started.",
        )
        logger.info("[9e82] aws_steampipe_collection_started")

        secret_ref = AWS_STEAMPIPE_SECRET_REF.qualified
        try:
            target = resolve_aws_collection_target()
        except SecretNotFoundError:
            message = (
                f"No runtime secret was loaded for {secret_ref!r}. Create a "
                f"{AWS_STEAMPIPE_SECRET_REF.key}{SECRET_SUFFIX} file under "
                "TAP_SECRETS_ROOT (local compose mounts this from "
                "'./tap_secrets') with kind 'aws_static_access_key', then "
                "restart the web container so tap-cares reloads runtime secrets."
            )
            self.record_error(
                _SITE_SECRET_MISSING,
                "SECRET_MISSING_FILE",
                message,
                message_data={
                    "secret_ref": secret_ref,
                    "expected_secret_filename": (f"{AWS_STEAMPIPE_SECRET_REF.key}{SECRET_SUFFIX}"),
                    "expected_secret_kind": "aws_static_access_key",
                },
            )
            self.summary = "AWS Steampipe collector secret is not loaded."
            logger.exception(
                "[cdbb] aws_steampipe_secret_missing secret_ref=%s",
                secret_ref,
            )
            raise
        except SecretError as exc:
            self.record_error(
                _SITE_SECRET_INVALID,
                "SECRET_INVALID",
                str(exc),
                message_data={"secret_ref": secret_ref},
            )
            self.summary = "AWS Steampipe collector secret is invalid."
            logger.exception(
                "[740d] aws_steampipe_secret_invalid secret_ref=%s",
                secret_ref,
            )
            raise
        except AwsSteampipeConfigError as exc:
            self.record_error(
                _SITE_TARGET_INVALID,
                "TARGET_INVALID",
                str(exc),
                message_data={"secret_ref": secret_ref},
            )
            self.summary = "AWS Steampipe collector secret is missing required " "region/account."
            logger.exception(
                "[78f2] aws_steampipe_target_invalid secret_ref=%s",
                secret_ref,
            )
            raise

        try:
            result = self.runner_cls().run_query_set(
                VPC_SUBNET_V0,
                region=target.primary_region,
                env=target.credentials.as_steampipe_env(region=target.primary_region),
                redaction_values=target.credentials.redaction_values(),
            )
        except SteampipeRunnerError as exc:
            self.record_error(
                _SITE_STEAMPIPE_FAILED,
                "STEAMPIPE_FAILED",
                str(exc),
                message_data=target.to_context(),
            )
            self.summary = f"AWS Steampipe run failed for account {target.account_id} " f"({AWS_COLLECTION_SCOPE})."
            logger.exception(
                "[f60f] aws_steampipe_runner_failed account=%s scope=%s",
                target.account_id,
                AWS_COLLECTION_SCOPE,
            )
            raise

        self.profile_result = result
        tables = {table: {"rows": len(rows)} for table, rows in sorted(result.rows_by_table.items())}
        self.record_info(
            _SITE_COLLECTED,
            "COLLECTED",
            f"AWS Steampipe {AWS_COLLECTION_SCOPE} collected.",
            message_data={
                **target.to_context(),
                "tables": tables,
                "warnings": result.warnings,
            },
        )
        logger.info(
            "[1d81] aws_steampipe_collected account=%s scope=%s tables=%s",
            target.account_id,
            AWS_COLLECTION_SCOPE,
            sorted(result.rows_by_table),
        )
        # Option A: every committed log call carries a bare site token, DEBUG
        # included (specs/spec-tap-logging.md req-tap-logging-site-ids).
        # Warnings are already redacted by the runner. (req-aws-steampipe-runner-6)
        logger.debug(
            "[8517] aws_steampipe run scope=%s account=%s region=%s tables=%s warnings=%s",
            AWS_COLLECTION_SCOPE,
            target.account_id,
            target.primary_region,
            tables,
            result.warnings,
        )

        vpc_rows = result.row_count("aws_vpc")
        subnet_rows = result.row_count("aws_vpc_subnet")
        self.summary = (
            f"Collected AWS {AWS_COLLECTION_SCOPE} (acct {target.account_id}): "
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
            "[58ca] aws_steampipe_collection_completed account=%s scope=%s",
            target.account_id,
            AWS_COLLECTION_SCOPE,
        )
