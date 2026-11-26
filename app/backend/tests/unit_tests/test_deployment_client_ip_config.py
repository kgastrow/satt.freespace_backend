"""The shipped deployment configs must resolve a per-client IP.

`get_client_ip` keys the brute-force lockout (src/api/auth.py) and the rate
limiter, not just audit rows. If a deployment cannot resolve a real client
address, every visitor shares one bucket and five failed logins from anyone
lock /auth/login for the whole deployment for 15 minutes.

That is not hypothetical: docker-compose.prod.yml ran uvicorn with no
--forwarded-allow-ips while nginx sat in a SEPARATE container, so uvicorn
trusted only 127.0.0.1, discarded the forwarded headers, and resolved every
request to the nginx container's address.

These assert the shipped configs, which no other test covers - the Python
behaviour is tested in tests/unit_tests/test_client_ip.py.
"""

import json
import pathlib

import yaml

from src.core.client_ip import APPEND_ONLY_HEADERS


BACKEND = pathlib.Path(__file__).resolve().parents[2]


def _compose():
    return yaml.safe_load((BACKEND / "docker-compose.prod.yml").read_text())


def test_compose_api_trusts_the_proxy_network_not_localhost():
    """nginx is a separate container, so 127.0.0.1 (uvicorn's default) is wrong."""
    command = _compose()["services"]["api"]["command"]
    assert "--forwarded-allow-ips" in command, (
        "docker-compose.prod.yml runs uvicorn without --forwarded-allow-ips. "
        "It defaults to trusting 127.0.0.1, but nginx is a separate container, "
        "so every request resolves to the nginx container address and the "
        "per-IP lockout becomes one global bucket."
    )


def test_compose_does_not_trust_every_peer():
    """'*' makes uvicorn return the client-controlled leftmost XFF entry."""
    command = _compose()["services"]["api"]["command"]
    assert "--forwarded-allow-ips=*" not in command.replace(" ", "")
    assert "--forwarded-allow-ips='*'" not in command


def test_compose_network_subnet_is_pinned_and_matches_the_allow_list():
    """An unpinned subnet makes the allow-list a guess that silently stops matching."""
    compose = _compose()
    subnets = [
        entry["subnet"]
        for entry in compose["networks"]["ayzer-webapp-network"]["ipam"]["config"]
    ]
    command = compose["services"]["api"]["command"]
    assert any(subnet in command for subnet in subnets), (
        f"--forwarded-allow-ips must name one of the pinned subnets {subnets}"
    )


def test_docker_config_example_sets_a_trusted_client_ip_header():
    server = json.loads((BACKEND / "config.docker.json.example").read_text())["server"]
    assert server.get("trusted_client_ip_header"), (
        "config.docker.json.example must set trusted_client_ip_header. This "
        "stack puts nginx in its own container, which is exactly the topology "
        "that collapses to a single lockout bucket without it."
    )


def test_no_shipped_config_trusts_an_append_only_header():
    """A client can prefix X-Forwarded-For, so its leftmost value is forgeable."""
    for name in ("config.json.example", "config.docker.json.example"):
        path = BACKEND / name
        if not path.exists():
            continue
        header = json.loads(path.read_text())["server"].get(
            "trusted_client_ip_header", ""
        )
        assert header.lower() not in APPEND_ONLY_HEADERS, (
            f"{name} trusts {header!r}, which proxies append to rather than "
            f"overwrite. Startup refuses this; the example must not suggest it."
        )
