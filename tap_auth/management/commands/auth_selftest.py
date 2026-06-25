"""`manage.py auth_selftest` — run provider self-tests (req-tap-auth-providers).

Probes every configured auth provider (``settings.TAP_AUTH_PROVIDERS``) the same
way ``CollectorBase`` self-tests probe collector upstreams: an offline phase
(config shape, secret presence/validity, local derivations) and, with ``--live``,
a network phase (IdP reachability / discovery-document checks). Prints a result
table and exits non-zero if any check FAILs — so it doubles as a boot/CI gate
and an operator's "what is wrong with auth right now" diagnostic.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from tap_auth.providers import ProviderConfig, SelfTestStatus, get_provider
from tap_auth.providers.base import ProviderError, SelfTestResult

_ICON = {
    SelfTestStatus.PASS: "PASS",
    SelfTestStatus.WARN: "WARN",
    SelfTestStatus.FAIL: "FAIL",
    SelfTestStatus.SKIP: "SKIP",
}


class Command(BaseCommand):
    help = "Run offline (and optionally live) self-tests for configured auth providers."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--live",
            action="store_true",
            default=False,
            help="Also run live network checks (IdP discovery-document reachability).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        live: bool = options["live"]
        raw_configs = getattr(settings, "TAP_AUTH_PROVIDERS", []) or []
        if not raw_configs:
            self.stdout.write("No auth providers configured (TAP_AUTH_PROVIDERS is empty).")
            return

        any_fail = False
        for raw in raw_configs:
            config = ProviderConfig.from_dict(raw)
            self.stdout.write(f"\n[{config.id}] type={config.type} live={live}")
            provider = get_provider(config.type)

            # Resolve secrets best-effort; a resolution failure becomes a FAIL
            # result inside self_test (secret_exists check), so swallow here.
            try:
                secrets = provider.resolve_secrets(config)
            except ProviderError:
                secrets = {}

            results: list[SelfTestResult] = provider.self_test(config, secrets, live=live)
            for r in results:
                if r.status is SelfTestStatus.FAIL:
                    any_fail = True
                docs = f"  ({r.docs_url})" if r.docs_url else ""
                self.stdout.write(f"  {_ICON[r.status]}  {r.phase.value:<7} {r.check}: {r.message}{docs}")

        if any_fail:
            raise CommandError("one or more provider self-tests FAILED")
        self.stdout.write(self.style.SUCCESS("\nAll provider self-tests passed (no FAILs)."))
