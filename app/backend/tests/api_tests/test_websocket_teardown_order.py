"""The order of the WebSocket endpoint's teardown steps is load-bearing.

Stopping the writer before dropping the pub/sub callback defeats the purpose of
both. The callback stays registered through `sender.stop()` AND all three
UNSUBSCRIBE round-trips, so every frame that arrives in that window — on the org
and platform channels, which are still subscribed while the user channel is
being torn down — is handed to a sender whose writer has already been cancelled.
Those frames are queued, never written and silently discarded, and once 64 of
them pile up the sender spawns a detached `_force_close` task against a socket
that is already dead.

Dropping the callback first closes the window: nothing can be offered to a
writer that is about to be stopped.
"""

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from src.core.security import create_access_token
from tests.api_tests.test_websocket_api import (
    create_test_app,
    mock_websocket_dependencies,
)


@pytest.mark.asyncio
async def test_endpoint_unsubscribes_before_it_stops_the_sender(
    async_session, test_user, test_organization
):
    from src.services.websocket.sender import ConnectionSender

    order: list[str] = []

    real_stop = ConnectionSender.stop

    async def recording_stop(self):
        order.append("sender.stop")
        await real_stop(self)

    app = create_test_app(async_session)
    token = create_access_token(
        user_id=str(test_user.id), organization_id=str(test_organization.id)
    )

    with mock_websocket_dependencies(async_session) as (_registry, mock_pubsub):

        async def recording_unsubscribe(**kwargs):
            order.append("pubsub.unsubscribe")
            return True

        mock_pubsub.unsubscribe_for_connection = AsyncMock(
            side_effect=recording_unsubscribe
        )

        with patch.object(ConnectionSender, "stop", recording_stop):
            with TestClient(app) as client:
                with client.websocket_connect("/ws") as websocket:
                    websocket.send_json({"type": "auth", "token": token})
                    assert websocket.receive_json() == {"type": "auth_success"}
                    websocket.send_json({"type": "ping"})
                    assert websocket.receive_json() == {"type": "pong"}

    assert order == ["pubsub.unsubscribe", "sender.stop"], (
        "the endpoint must drop its pub/sub callback BEFORE stopping the "
        f"writer; observed teardown order was {order}"
    )
