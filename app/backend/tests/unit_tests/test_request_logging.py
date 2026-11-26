"""
Unit tests for request/response logging middleware and CRUD operations.
"""

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import pytest

from src.crud.request_log import (
    create_request_log,
    delete_old_request_logs,
    get_request_log_by_id,
    get_request_logs,
)
from src.middleware.request_response_logging import (
    RequestResponseLoggingMiddleware,
    sanitize_data,
    setup_request_logger,
    setup_request_response_logging,
)
from src.services.request_log_writer import write_request_log_to_db


class TestSanitizeData:
    """Test data sanitization functions."""

    def test_sanitize_password(self):
        """Test that passwords are sanitized."""
        data = {"username": "test", "password": "secret123"}
        result = sanitize_data(data)
        assert result["username"] == "test"
        assert result["password"] == "secr****"

    def test_sanitize_token(self):
        """Test that tokens are sanitized."""
        data = {"access_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"}
        result = sanitize_data(data)
        assert result["access_token"] == "Bear****"

    def test_sanitize_api_key(self):
        """Test that API keys are sanitized."""
        data = {"api_key": "sk-1234567890abcdef"}
        result = sanitize_data(data)
        assert result["api_key"] == "sk-1****"

    def test_sanitize_nested_data(self):
        """Test that nested data structures are sanitized."""
        data = {
            "user": {
                "email": "test@example.com",
                "password": "secret123",
            },
            "metadata": {
                "api_key": "sk-1234567890",
            },
        }
        result = sanitize_data(data)
        assert result["user"]["email"] == "test@example.com"
        assert result["user"]["password"] == "secr****"
        assert result["metadata"]["api_key"] == "sk-1****"

    def test_sanitize_list_data(self):
        """Test that lists containing dicts are sanitized."""
        data = {
            "users": [
                {"username": "user1", "password": "pass1"},
                {"username": "user2", "token": "token123"},
            ]
        }
        result = sanitize_data(data)
        assert result["users"][0]["username"] == "user1"
        assert result["users"][0]["password"] == "pass****"
        assert result["users"][1]["username"] == "user2"
        assert result["users"][1]["token"] == "toke****"

    def test_sanitize_short_password(self):
        """Test that short passwords are fully masked."""
        data = {"password": "123"}
        result = sanitize_data(data)
        assert result["password"] == "********"

    def test_sanitize_empty_dict(self):
        """Test that empty dict returns empty dict."""
        result = sanitize_data({})
        assert result == {}

    def test_sanitize_none(self):
        """Test that None returns empty dict."""
        result = sanitize_data(None)
        assert result == {}

    def test_sanitize_case_insensitive(self):
        """Test that sanitization is case-insensitive."""
        data = {
            "Password": "secret",
            "ACCESS_TOKEN": "token123",
            "Api_Key": "key123",
        }
        result = sanitize_data(data)
        assert result["Password"] == "secr****"
        assert result["ACCESS_TOKEN"] == "toke****"
        assert result["Api_Key"] == "key1****"


class TestSetupRequestLogger:
    """Test request logger setup."""

    def test_creates_logger(self):
        """Test that logger is created with correct name."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            logger = setup_request_logger(tmp.name)
            assert logger.name == "request_response_logger"
            assert logger.level == 20  # INFO level
            os.unlink(tmp.name)

    def test_avoids_duplicate_handlers(self):
        """Test that calling setup twice doesn't duplicate handlers."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            logger1 = setup_request_logger(tmp.name)
            initial_handler_count = len(logger1.handlers)

            logger2 = setup_request_logger(tmp.name)
            assert len(logger2.handlers) == initial_handler_count
            os.unlink(tmp.name)


@pytest.mark.asyncio
class TestRequestResponseLoggingMiddleware:
    """Test the request/response logging middleware."""

    async def test_middleware_logs_request(self, caplog):
        """Test that middleware logs requests correctly."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        # Mock config_cache to return enabled config
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.db_enabled = False
        mock_config.max_body_size = 10240

        with patch(
            "src.middleware.request_response_logging.settings"
        ) as mock_settings, patch(
            "src.services.config_cache.get_request_logging_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ):
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(app, max_body_size=10240)

            # Create mock request
            mock_request = Mock(spec=Request)
            mock_request.method = "POST"
            mock_request.url.path = "/test"
            mock_request.client.host = "127.0.0.1"
            mock_request.headers.get.return_value = "TestAgent/1.0"

            # Mock request body
            request_body = json.dumps({"username": "test", "password": "secret123"})
            mock_request.body = AsyncMock(return_value=request_body.encode())

            # Mock call_next to return a response
            mock_response = JSONResponse(
                content={"status": "ok"},
                status_code=200,
            )

            async def mock_call_next(request):
                return mock_response

            # Process request
            await middleware.dispatch(mock_request, mock_call_next)

            # Verify log contains expected data from captured logs
            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) > 0

            log_entry = json.loads(log_messages[0])
            assert log_entry["path"] == "/test"
            assert log_entry["method"] == "POST"
            assert log_entry["status_code"] == 200
            assert "duration_ms" in log_entry
            assert log_entry["ip_address"] == "127.0.0.1"

            # Verify sensitive data is sanitized
            assert log_entry["request_body"]["password"] == "secr****"
            assert "secret123" not in log_messages[0]

            # Cleanup
            os.unlink(log_file)

    async def test_middleware_excludes_paths(self, caplog):
        """Test that excluded paths are not logged."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        with patch("src.middleware.request_response_logging.settings") as mock_settings:
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(
                app,
                excluded_paths={"/health"},
            )

            # Create mock request
            mock_request = Mock(spec=Request)
            mock_request.method = "GET"
            mock_request.url.path = "/health"

            # Mock call_next
            async def mock_call_next(request):
                return JSONResponse(content={"status": "ok"})

            # Process request
            await middleware.dispatch(mock_request, mock_call_next)

            # Verify nothing was logged
            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) == 0

            # Cleanup
            os.unlink(log_file)

    async def test_middleware_truncates_large_bodies(self, caplog):
        """Test that large request bodies are truncated."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        # Mock config_cache to return enabled config with 1KB limit
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.db_enabled = False
        mock_config.max_body_size = 1024

        with patch(
            "src.middleware.request_response_logging.settings"
        ) as mock_settings, patch(
            "src.services.config_cache.get_request_logging_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ):
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(
                app,
                max_body_size=1024,  # 1KB limit
            )

            # Create mock request with large body
            mock_request = Mock(spec=Request)
            mock_request.method = "POST"
            mock_request.url.path = "/test"
            mock_request.client.host = "127.0.0.1"
            mock_request.headers.get.return_value = "TestAgent/1.0"

            large_body = json.dumps({"data": "x" * 10000})
            mock_request.body = AsyncMock(return_value=large_body.encode())

            # Mock call_next
            async def mock_call_next(request):
                return JSONResponse(content={"status": "ok"})

            # Process request
            await middleware.dispatch(mock_request, mock_call_next)

            # Verify truncation message is present
            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) > 0

            log_entry = json.loads(log_messages[0])
            assert "truncated" in log_entry["request_body"]
            assert "Body too large" in log_entry["request_body"]["truncated"]

            # Cleanup
            os.unlink(log_file)

    async def test_middleware_handles_non_json_body(self, caplog):
        """Test that non-JSON request bodies are handled gracefully."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        # Mock config_cache to return enabled config
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.db_enabled = False
        mock_config.max_body_size = 10240

        with patch(
            "src.middleware.request_response_logging.settings"
        ) as mock_settings, patch(
            "src.services.config_cache.get_request_logging_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ):
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(app)

            # Create mock request with binary body
            mock_request = Mock(spec=Request)
            mock_request.method = "POST"
            mock_request.url.path = "/upload"
            mock_request.client.host = "127.0.0.1"
            mock_request.headers.get.return_value = "TestAgent/1.0"

            binary_body = b"\x89\x50\x4E\x47"  # PNG header
            mock_request.body = AsyncMock(return_value=binary_body)

            # Mock call_next
            async def mock_call_next(request):
                return JSONResponse(content={"status": "ok"})

            # Process request
            await middleware.dispatch(mock_request, mock_call_next)

            # Verify non-JSON handling
            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) > 0

            log_entry = json.loads(log_messages[0])
            assert "raw" in log_entry["request_body"]
            assert "non-json data" in log_entry["request_body"]["raw"]

            # Cleanup
            os.unlink(log_file)

    async def test_middleware_captures_duration(self, caplog):
        """Test that middleware captures request duration."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        # Mock config_cache to return enabled config
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.db_enabled = False
        mock_config.max_body_size = 10240

        with patch(
            "src.middleware.request_response_logging.settings"
        ) as mock_settings, patch(
            "src.services.config_cache.get_request_logging_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ):
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(app)

            # Create mock request
            mock_request = Mock(spec=Request)
            mock_request.method = "GET"
            mock_request.url.path = "/test"
            mock_request.client.host = "127.0.0.1"
            mock_request.headers.get.return_value = "TestAgent/1.0"

            # Mock call_next
            async def mock_call_next(request):
                return JSONResponse(content={"status": "ok"})

            # Process request
            await middleware.dispatch(mock_request, mock_call_next)

            # Verify duration is captured
            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) > 0

            log_entry = json.loads(log_messages[0])
            assert "duration_ms" in log_entry
            assert isinstance(log_entry["duration_ms"], (int, float))
            assert log_entry["duration_ms"] >= 0

            # Cleanup
            os.unlink(log_file)


class TestSetupRequestResponseLogging:
    """Test the setup function."""

    def test_setup_when_enabled(self):
        """Test that middleware is added when enabled."""
        app = FastAPI()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            with patch(
                "src.middleware.request_response_logging.settings"
            ) as mock_settings:
                mock_settings.REQUEST_LOGGING_ENABLED = True
                mock_settings.REQUEST_LOGGING_FILE = tmp.name
                mock_settings.REQUEST_LOGGING_MAX_BODY_SIZE = 10240

                initial_middleware_count = len(app.user_middleware)
                setup_request_response_logging(app)

                # Verify middleware was added
                assert len(app.user_middleware) == initial_middleware_count + 1

            os.unlink(tmp.name)

    def test_setup_when_disabled(self):
        """Test that middleware is added even when disabled (checks config dynamically)."""
        app = FastAPI()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            with patch(
                "src.middleware.request_response_logging.settings"
            ) as mock_settings:
                mock_settings.REQUEST_LOGGING_ENABLED = False
                mock_settings.REQUEST_LOGGING_FILE = tmp.name
                mock_settings.REQUEST_LOGGING_MAX_BODY_SIZE = 10240

                initial_middleware_count = len(app.user_middleware)
                setup_request_response_logging(app)

                # Middleware is always added now (checks config dynamically per-request)
                assert len(app.user_middleware) == initial_middleware_count + 1

            os.unlink(tmp.name)

    def test_setup_with_excluded_paths(self):
        """Test that excluded paths are passed to middleware."""
        app = FastAPI()

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            with patch(
                "src.middleware.request_response_logging.settings"
            ) as mock_settings:
                mock_settings.REQUEST_LOGGING_ENABLED = True
                mock_settings.REQUEST_LOGGING_FILE = tmp.name
                mock_settings.REQUEST_LOGGING_MAX_BODY_SIZE = 10240

                excluded_paths = {"/health", "/metrics"}
                setup_request_response_logging(app, excluded_paths=excluded_paths)

                # Middleware was added
                assert len(app.user_middleware) > 0

            os.unlink(tmp.name)


# ========== CRUD Tests ==========


@pytest.mark.asyncio
class TestRequestLogCRUD:
    """Test request log CRUD operations."""

    async def test_create_request_log(
        self, async_session, test_organization, test_user
    ):
        """Test creating a request log entry."""
        request_log = await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/users",
            status_code=200,
            duration_ms=123,
            request_body={"param": "value"},
            response_body={"status": "ok"},
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert request_log.id is not None
        assert request_log.method == "GET"
        assert request_log.path == "/api/v1/users"
        assert request_log.status_code == 200
        assert request_log.duration_ms == 123
        assert request_log.request_body == {"param": "value"}
        assert request_log.response_body == {"status": "ok"}
        assert request_log.ip_address == "192.168.1.1"
        assert request_log.user_agent == "Mozilla/5.0"
        assert str(request_log.organization_id) == str(test_organization.id)
        assert str(request_log.user_id) == str(test_user.id)
        assert request_log.deleted_time is None

    async def test_create_request_log_unauthenticated(self, async_session):
        """Test creating request log for unauthenticated request."""
        request_log = await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/auth/login",
            status_code=200,
            duration_ms=50,
            ip_address="10.0.0.1",
        )

        assert request_log.id is not None
        assert request_log.organization_id is None
        assert request_log.user_id is None
        assert request_log.method == "POST"
        assert request_log.path == "/api/v1/auth/login"

    async def test_get_request_logs(self, async_session, test_organization, test_user):
        """Test retrieving request logs with cursor-based pagination."""
        # Create multiple request logs
        for i in range(5):
            await create_request_log(
                session=async_session,
                method="GET",
                path=f"/api/v1/test/{i}",
                status_code=200,
                duration_ms=100 + i,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        # First page
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            limit=3,
        )

        assert len(logs) == 3
        assert has_more is True
        assert next_cursor is not None

        # Second page using cursor
        logs2, next_cursor2, has_more2 = await get_request_logs(
            session=async_session,
            limit=3,
            cursor=next_cursor,
        )

        assert len(logs2) == 2
        assert has_more2 is False
        assert next_cursor2 is None

    async def test_get_request_logs_filter_by_method(
        self, async_session, test_organization, test_user
    ):
        """Test filtering request logs by HTTP method."""
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/test",
            status_code=201,
            duration_ms=150,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            method="GET",
        )

        assert len(logs) == 1
        assert all(log.method == "GET" for log in logs)

    async def test_get_request_logs_filter_by_path_pattern(
        self, async_session, test_organization, test_user
    ):
        """Test filtering request logs by path pattern."""
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/users",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/roles",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            path_pattern="users",
        )

        assert len(logs) == 1
        assert all("users" in log.path for log in logs)

    async def test_get_request_logs_filter_by_status_code_range(
        self, async_session, test_organization, test_user
    ):
        """Test filtering request logs by status code range."""
        # Create logs with different status codes
        for status_code in [200, 201, 400, 404, 500]:
            await create_request_log(
                session=async_session,
                method="GET",
                path="/api/v1/test",
                status_code=status_code,
                duration_ms=100,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        # Filter for error responses (4xx and 5xx)
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            status_code_min=400,
        )

        assert len(logs) == 3
        assert all(log.status_code >= 400 for log in logs)

        # Filter for success responses (2xx)
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            status_code_min=200,
            status_code_max=299,
        )

        assert len(logs) == 2
        assert all(200 <= log.status_code <= 299 for log in logs)

    async def test_get_request_logs_filter_by_date_range(
        self, async_session, test_organization, test_user
    ):
        """Test filtering request logs by date range."""
        # Create logs at different times (we'll use the created_time field)
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        # Use a date range that includes the log
        now = datetime.now(timezone.utc)
        date_from = now - timedelta(hours=1)
        date_to = now + timedelta(hours=1)

        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            date_from=date_from,
            date_to=date_to,
        )

        assert len(logs) >= 1
        # Ensure comparison with timezone-aware dates
        for log in logs:
            created = log.created_time
            if created.tzinfo is None:
                # If created_time is naive, make it aware
                created = created.replace(tzinfo=timezone.utc)
            assert date_from <= created <= date_to

    async def test_get_request_logs_filter_by_organization(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test filtering request logs by organization."""
        # Create logs for different organizations
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(second_organization.id),
        )

        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert len(logs) == 1
        assert all(
            str(log.organization_id) == str(test_organization.id) for log in logs
        )

    async def test_get_request_logs_filter_by_user(
        self, async_session, test_organization, test_user, second_org_user
    ):
        """Test filtering request logs by user."""
        # Create logs for different users
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(second_org_user.id),
        )

        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            user_id=str(test_user.id),
        )

        assert len(logs) == 1
        assert all(str(log.user_id) == str(test_user.id) for log in logs)

    async def test_get_request_log_by_id(
        self, async_session, test_organization, test_user
    ):
        """Test retrieving a single request log by ID."""
        request_log = await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/test",
            status_code=201,
            duration_ms=200,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        retrieved_log = await get_request_log_by_id(
            session=async_session,
            request_log_id=str(request_log.id),
        )

        assert retrieved_log is not None
        assert str(retrieved_log.id) == str(request_log.id)
        assert retrieved_log.method == "POST"
        assert retrieved_log.path == "/api/v1/test"

    async def test_get_request_log_by_id_not_found(self, async_session):
        """Test retrieving non-existent request log returns None."""
        import uuid

        fake_id = str(uuid.uuid4())
        retrieved_log = await get_request_log_by_id(
            session=async_session,
            request_log_id=fake_id,
        )

        assert retrieved_log is None

    async def test_delete_old_request_logs(
        self, async_session, test_organization, test_user
    ):
        """Test soft-deleting old request logs."""
        # Create some request logs
        for i in range(5):
            await create_request_log(
                session=async_session,
                method="GET",
                path=f"/api/v1/test/{i}",
                status_code=200,
                duration_ms=100,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        # Set cutoff date to delete all logs created before "now + 1 hour"
        cutoff_date = datetime.now(timezone.utc) + timedelta(hours=1)

        deleted_count = await delete_old_request_logs(
            session=async_session,
            cutoff_date=cutoff_date,
        )

        assert deleted_count == 5

        # Verify logs are soft-deleted (should return 0 active logs)
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
        )

        assert len(logs) == 0

    async def test_delete_old_request_logs_respects_cutoff(
        self, async_session, test_organization, test_user
    ):
        """Test that delete only removes logs older than cutoff."""
        # Create some request logs
        for i in range(3):
            await create_request_log(
                session=async_session,
                method="GET",
                path=f"/api/v1/test/{i}",
                status_code=200,
                duration_ms=100,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        # Set cutoff date to the past, so no logs should be deleted
        cutoff_date = datetime.now(timezone.utc) - timedelta(hours=1)

        deleted_count = await delete_old_request_logs(
            session=async_session,
            cutoff_date=cutoff_date,
        )

        assert deleted_count == 0

        # Verify all logs still exist
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
        )

        assert len(logs) == 3


# ========== Database Writer Service Tests ==========


@pytest.mark.asyncio
class TestRequestLogWriter:
    """Test request log database writer service."""

    async def test_write_request_log_to_db_with_auth(
        self, async_session, test_organization, test_user
    ):
        """Test writing request log to database with JWT authentication."""
        import jwt

        from src.core.config import settings

        # Create a JWT token
        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        authorization_header = f"Bearer {token}"

        await write_request_log_to_db(
            session=async_session,
            method="GET",
            path="/api/v1/users",
            status_code=200,
            duration_ms=150,
            request_body={"param": "value"},
            response_body={"status": "ok"},
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            authorization_header=authorization_header,
        )

        # Verify the log was created
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        assert len(logs) == 1
        assert logs[0].method == "GET"
        assert logs[0].path == "/api/v1/users"
        assert logs[0].status_code == 200
        assert logs[0].duration_ms == 150
        assert str(logs[0].organization_id) == str(test_organization.id)
        assert str(logs[0].user_id) == str(test_user.id)

    async def test_write_request_log_to_db_without_auth(self, async_session):
        """Test writing request log to database without authentication."""
        await write_request_log_to_db(
            session=async_session,
            method="POST",
            path="/api/v1/auth/login",
            status_code=200,
            duration_ms=50,
            ip_address="10.0.0.1",
            user_agent="TestAgent/1.0",
            authorization_header=None,
        )

        # Verify the log was created without user/org context
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
        )

        assert len(logs) == 1
        assert logs[0].method == "POST"
        assert logs[0].path == "/api/v1/auth/login"
        assert logs[0].organization_id is None
        assert logs[0].user_id is None

    async def test_write_request_log_to_db_with_invalid_token(self, async_session):
        """Test writing request log with invalid JWT token (should still log without user context)."""
        authorization_header = "Bearer invalid.token.here"

        await write_request_log_to_db(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=401,
            duration_ms=10,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            authorization_header=authorization_header,
        )

        # Verify the log was created without user/org context
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
        )

        assert len(logs) == 1
        assert logs[0].organization_id is None
        assert logs[0].user_id is None

    async def test_write_request_log_to_db_handles_errors_gracefully(
        self, async_session
    ):
        """Test that database errors don't crash the writer."""
        # Close the session to simulate a database error
        await async_session.close()

        # This should not raise an exception
        try:
            await write_request_log_to_db(
                session=async_session,
                method="GET",
                path="/api/v1/test",
                status_code=200,
                duration_ms=100,
            )
        except Exception:
            pytest.fail(
                "write_request_log_to_db should handle database errors gracefully"
            )

    async def test_write_request_log_to_db_with_request_body(
        self, async_session, test_organization, test_user
    ):
        """Test writing request log with sanitized request body."""
        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        authorization_header = f"Bearer {token}"

        request_body = {"username": "test", "data": "value"}

        await write_request_log_to_db(
            session=async_session,
            method="POST",
            path="/api/v1/users",
            status_code=201,
            duration_ms=200,
            request_body=request_body,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            authorization_header=authorization_header,
        )

        # Verify the log was created with request body
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert len(logs) == 1
        assert logs[0].request_body == request_body


# ========== API Tests ==========


@pytest.mark.asyncio
class TestRequestLogAPI:
    """Test request log API endpoints."""

    async def test_list_request_logs_as_super_admin(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test listing request logs as super admin."""
        # Create some request logs
        for i in range(3):
            await create_request_log(
                session=async_session,
                method="GET",
                path=f"/api/v1/test/{i}",
                status_code=200,
                duration_ms=100 + i,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "has_more" in data
        assert "next_cursor" in data
        assert len(data["items"]) >= 3

    async def test_list_request_logs_with_method_filter(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test filtering request logs by HTTP method."""
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/test",
            status_code=201,
            duration_ms=150,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        response = await client.get(
            "/api/v1/admin/request-logs?method=GET",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert all(item["method"] == "GET" for item in data["items"])

    async def test_list_request_logs_with_path_filter(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test filtering request logs by path pattern."""
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/users",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/roles",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        response = await client.get(
            "/api/v1/admin/request-logs?path=users",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert all("users" in item["path"] for item in data["items"])

    async def test_list_request_logs_with_status_code_filter(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test filtering request logs by status code range."""
        # Create logs with different status codes
        for status_code in [200, 201, 400, 500]:
            await create_request_log(
                session=async_session,
                method="GET",
                path="/api/v1/test",
                status_code=status_code,
                duration_ms=100,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        # Filter for error responses (400+)
        response = await client.get(
            "/api/v1/admin/request-logs?status_code_min=400",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 2
        assert all(item["status_code"] >= 400 for item in data["items"])

    async def test_list_request_logs_with_organization_filter(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        second_organization,
        test_user,
    ):
        """Test filtering request logs by organization."""
        # Create logs for different organizations
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(second_organization.id),
        )

        response = await client.get(
            f"/api/v1/admin/request-logs?organization_id={test_organization.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert all(
            item["organization_id"] == str(test_organization.id)
            for item in data["items"]
            if item["organization_id"] is not None
        )

    async def test_list_request_logs_with_user_filter(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
        second_org_user,
    ):
        """Test filtering request logs by user."""
        # Create logs for different users
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )
        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(second_org_user.id),
        )

        response = await client.get(
            f"/api/v1/admin/request-logs?user_id={test_user.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1
        assert all(
            item["user_id"] == str(test_user.id)
            for item in data["items"]
            if item["user_id"] is not None
        )

    async def test_list_request_logs_with_pagination(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test cursor-based pagination of request logs."""
        # Create multiple request logs
        for i in range(10):
            await create_request_log(
                session=async_session,
                method="GET",
                path=f"/api/v1/test/{i}",
                status_code=200,
                duration_ms=100 + i,
                organization_id=str(test_organization.id),
                user_id=str(test_user.id),
            )

        # Get first page
        response = await client.get(
            "/api/v1/admin/request-logs?limit=5",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["limit"] == 5
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

        # Get second page using cursor
        response2 = await client.get(
            f"/api/v1/admin/request-logs?limit=5&cursor={data['next_cursor']}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["items"]) == 5
        # Verify no duplicate items between pages
        first_page_ids = {item["id"] for item in data["items"]}
        second_page_ids = {item["id"] for item in data2["items"]}
        assert first_page_ids.isdisjoint(second_page_ids)

    async def test_list_request_logs_requires_super_admin(
        self, client, test_jwt_token, async_session
    ):
        """Test that listing request logs requires super admin access."""
        response = await client.get(
            "/api/v1/admin/request-logs",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    async def test_list_request_logs_requires_authentication(
        self, client, async_session
    ):
        """Test that listing request logs requires authentication."""
        response = await client.get("/api/v1/admin/request-logs")

        assert response.status_code == 401

    async def test_get_request_log_by_id_as_super_admin(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test getting a single request log by ID as super admin."""
        request_log = await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/test",
            status_code=201,
            duration_ms=200,
            request_body={"param": "value"},
            response_body={"status": "ok"},
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        response = await client.get(
            f"/api/v1/admin/request-logs/{request_log.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(request_log.id)
        assert data["method"] == "POST"
        assert data["path"] == "/api/v1/test"
        assert data["status_code"] == 201
        assert data["duration_ms"] == 200
        assert data["request_body"] == {"param": "value"}
        assert data["response_body"] == {"status": "ok"}
        assert data["organization_id"] == str(test_organization.id)
        assert data["user_id"] == str(test_user.id)

    async def test_get_request_log_by_id_not_found(
        self, client, test_super_admin_token, async_session
    ):
        """Test getting non-existent request log returns 404."""
        import uuid

        fake_id = uuid.uuid4()
        response = await client.get(
            f"/api/v1/admin/request-logs/{fake_id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 404

    async def test_get_request_log_by_id_requires_super_admin(
        self, client, test_jwt_token, async_session, test_organization, test_user
    ):
        """Test that getting request log by ID requires super admin access."""
        request_log = await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        response = await client.get(
            f"/api/v1/admin/request-logs/{request_log.id}",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    async def test_get_request_log_by_id_requires_authentication(
        self, client, async_session, test_organization, test_user
    ):
        """Test that getting request log by ID requires authentication."""
        request_log = await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
        )

        response = await client.get(f"/api/v1/admin/request-logs/{request_log.id}")

        assert response.status_code == 401

    async def test_trigger_cleanup_as_super_admin(
        self, client, test_super_admin_token, async_session, monkeypatch
    ):
        """Test manually triggering cleanup job as super admin."""
        from src.services.tasks import task_queue

        # Mock the enqueue_job method
        mock_job_id = "test-job-123"
        original_enqueue = task_queue.enqueue_job

        async def mock_enqueue_job(task_name, *args, **kwargs):
            if task_name == "cleanup_old_request_logs_task":
                return mock_job_id
            return await original_enqueue(task_name, *args, **kwargs)

        monkeypatch.setattr(task_queue, "enqueue_job", mock_enqueue_job)

        response = await client.post(
            "/api/v1/admin/request-logs/cleanup",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert data["job_id"] == mock_job_id

    async def test_trigger_cleanup_requires_super_admin(
        self, client, test_jwt_token, async_session
    ):
        """Test that triggering cleanup requires super admin access."""
        response = await client.post(
            "/api/v1/admin/request-logs/cleanup",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    async def test_trigger_cleanup_requires_authentication(self, client, async_session):
        """Test that triggering cleanup requires authentication."""
        response = await client.post("/api/v1/admin/request-logs/cleanup")

        assert response.status_code == 401


# ========== Error Traceback Tests ==========


@pytest.mark.asyncio
class TestErrorTracebackCapture:
    """Test error traceback capture functionality for 500 errors."""

    async def test_create_request_log_with_traceback(
        self, async_session, test_organization, test_user
    ):
        """Test creating a request log with error traceback."""
        traceback_text = """Traceback (most recent call last):
  File "/app/backend/src/api/test.py", line 42, in test_handler
    raise ValueError("Test error")
ValueError: Test error"""

        request_log = await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/test",
            status_code=500,
            duration_ms=50,
            ip_address="192.168.1.1",
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=traceback_text,
        )

        assert request_log.id is not None
        assert request_log.status_code == 500
        assert request_log.error_traceback == traceback_text

    async def test_create_request_log_without_traceback(
        self, async_session, test_organization, test_user
    ):
        """Test creating a request log without error traceback (successful request)."""
        request_log = await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=200,
            duration_ms=100,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=None,
        )

        assert request_log.id is not None
        assert request_log.status_code == 200
        assert request_log.error_traceback is None

    async def test_get_request_log_by_id_returns_traceback(
        self, async_session, test_organization, test_user
    ):
        """Test that getting a request log by ID returns the error traceback."""
        traceback_text = "ValueError: Something went wrong\n  at function_name()"

        request_log = await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/error-endpoint",
            status_code=500,
            duration_ms=25,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=traceback_text,
        )

        retrieved_log = await get_request_log_by_id(
            session=async_session,
            request_log_id=str(request_log.id),
        )

        assert retrieved_log is not None
        assert retrieved_log.error_traceback == traceback_text

    async def test_get_request_logs_returns_traceback(
        self, async_session, test_organization, test_user
    ):
        """Test that listing request logs returns error traceback."""
        traceback_text = "KeyError: 'missing_key'"

        await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/test",
            status_code=500,
            duration_ms=15,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=traceback_text,
        )

        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            status_code_min=500,
        )

        assert len(logs) >= 1
        error_log = next((log for log in logs if log.status_code == 500), None)
        assert error_log is not None
        assert error_log.error_traceback == traceback_text


@pytest.mark.asyncio
class TestErrorTracebackWriter:
    """Test error traceback handling in the request log writer service."""

    async def test_write_request_log_with_traceback(
        self, async_session, test_organization, test_user
    ):
        """Test writing request log with error traceback to database."""
        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        authorization_header = f"Bearer {token}"
        traceback_text = """Traceback (most recent call last):
  File "test.py", line 10, in test
    raise Exception("Test")
Exception: Test"""

        await write_request_log_to_db(
            session=async_session,
            method="POST",
            path="/api/v1/failing-endpoint",
            status_code=500,
            duration_ms=100,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            authorization_header=authorization_header,
            error_traceback=traceback_text,
        )

        # Verify the log was created with traceback
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
            organization_id=str(test_organization.id),
        )

        assert len(logs) == 1
        assert logs[0].status_code == 500
        assert logs[0].error_traceback == traceback_text

    async def test_write_request_log_without_traceback(self, async_session):
        """Test writing request log without error traceback."""
        await write_request_log_to_db(
            session=async_session,
            method="GET",
            path="/api/v1/healthy-endpoint",
            status_code=200,
            duration_ms=50,
            ip_address="10.0.0.1",
            user_agent="TestAgent/1.0",
            authorization_header=None,
            error_traceback=None,
        )

        # Verify the log was created without traceback
        logs, next_cursor, has_more = await get_request_logs(
            session=async_session,
        )

        assert len(logs) == 1
        assert logs[0].status_code == 200
        assert logs[0].error_traceback is None


@pytest.mark.asyncio
class TestErrorTracebackAPI:
    """Test error traceback in API responses."""

    async def test_get_request_log_with_traceback_as_super_admin(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test getting a request log with error traceback via API."""
        traceback_text = """Traceback (most recent call last):
  File "/app/src/api/endpoint.py", line 55, in handler
    result = process_data(data)
  File "/app/src/services/processor.py", line 23, in process_data
    raise ValueError("Invalid data format")
ValueError: Invalid data format"""

        request_log = await create_request_log(
            session=async_session,
            method="POST",
            path="/api/v1/process",
            status_code=500,
            duration_ms=120,
            request_body={"data": "invalid"},
            response_body={"error": "Internal server error"},
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=traceback_text,
        )

        response = await client.get(
            f"/api/v1/admin/request-logs/{request_log.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(request_log.id)
        assert data["status_code"] == 500
        assert data["error_traceback"] == traceback_text

    async def test_list_request_logs_includes_traceback(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test that listing request logs includes error traceback field."""
        traceback_text = "Exception: Something failed"

        await create_request_log(
            session=async_session,
            method="DELETE",
            path="/api/v1/resource/123",
            status_code=500,
            duration_ms=80,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=traceback_text,
        )

        response = await client.get(
            "/api/v1/admin/request-logs?status_code_min=500",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

        error_item = next(
            (item for item in data["items"] if item["status_code"] == 500), None
        )
        assert error_item is not None
        assert error_item["error_traceback"] == traceback_text

    async def test_request_log_without_traceback_returns_null(
        self,
        client,
        test_super_admin_token,
        async_session,
        test_organization,
        test_user,
    ):
        """Test that successful requests have null error_traceback."""
        request_log = await create_request_log(
            session=async_session,
            method="GET",
            path="/api/v1/healthy",
            status_code=200,
            duration_ms=50,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            error_traceback=None,
        )

        response = await client.get(
            f"/api/v1/admin/request-logs/{request_log.id}",
            headers={"Authorization": test_super_admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status_code"] == 200
        assert data["error_traceback"] is None


@pytest.mark.asyncio
class TestMiddlewareTracebackCapture:
    """Test that middleware captures stack traces on exceptions."""

    async def test_middleware_captures_traceback_on_exception(self, caplog):
        """Test that middleware captures full stack trace when an exception occurs."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        # Mock config_cache to return enabled config
        mock_config = Mock()
        mock_config.enabled = True
        mock_config.db_enabled = False
        mock_config.max_body_size = 10240

        with patch(
            "src.middleware.request_response_logging.settings"
        ) as mock_settings, patch(
            "src.services.config_cache.get_request_logging_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ):
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(app, max_body_size=10240)

            # Create mock request
            mock_request = Mock(spec=Request)
            mock_request.method = "POST"
            mock_request.url.path = "/api/v1/failing"
            mock_request.client.host = "127.0.0.1"
            mock_request.headers.get.return_value = "TestAgent/1.0"
            mock_request.body = AsyncMock(return_value=b'{"test": "data"}')

            # Mock call_next to raise an exception
            async def mock_call_next_with_error(request):
                raise ValueError("Intentional test error for traceback capture")

            # Process request - should raise but log the traceback
            with pytest.raises(ValueError):
                await middleware.dispatch(mock_request, mock_call_next_with_error)

            # Verify log contains traceback
            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) > 0

            log_entry = json.loads(log_messages[0])
            assert log_entry["status_code"] == 500
            assert "error_traceback" in log_entry
            assert "ValueError" in log_entry["error_traceback"]
            assert (
                "Intentional test error for traceback capture"
                in log_entry["error_traceback"]
            )
            assert "Traceback" in log_entry["error_traceback"]

            # Cleanup
            os.unlink(log_file)

    async def test_middleware_no_traceback_on_success(self, caplog):
        """Test that successful requests don't have error_traceback in logs."""
        import logging

        caplog.set_level(logging.INFO, logger="request_response_logger")

        app = FastAPI()

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log") as tmp:
            log_file = tmp.name

        mock_config = Mock()
        mock_config.enabled = True
        mock_config.db_enabled = False
        mock_config.max_body_size = 10240

        with patch(
            "src.middleware.request_response_logging.settings"
        ) as mock_settings, patch(
            "src.services.config_cache.get_request_logging_config",
            new_callable=AsyncMock,
            return_value=mock_config,
        ):
            mock_settings.REQUEST_LOGGING_FILE = log_file
            mock_settings.REQUEST_LOGGING_ENABLED = True

            middleware = RequestResponseLoggingMiddleware(app, max_body_size=10240)

            mock_request = Mock(spec=Request)
            mock_request.method = "GET"
            mock_request.url.path = "/api/v1/success"
            mock_request.client.host = "127.0.0.1"
            mock_request.headers.get.return_value = "TestAgent/1.0"

            mock_response = JSONResponse(content={"status": "ok"}, status_code=200)

            async def mock_call_next(request):
                return mock_response

            await middleware.dispatch(mock_request, mock_call_next)

            log_messages = [record.message for record in caplog.records]
            assert len(log_messages) > 0

            log_entry = json.loads(log_messages[0])
            assert log_entry["status_code"] == 200
            # error_traceback should not be present in the log for successful requests
            assert (
                "error_traceback" not in log_entry
                or log_entry.get("error_traceback") is None
            )

            os.unlink(log_file)
