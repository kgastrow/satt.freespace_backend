"""
Tests for Query DSL parameter parsing utilities.
"""

from unittest.mock import MagicMock

from fastapi import HTTPException
import pytest

from src.core.query_params import (
    FilterOperator,
    FilterSpec,
    get_pagination_params,
    get_search_param,
    parse_filters,
    parse_sort,
)


class TestFilterSpec:
    """Tests for FilterSpec dataclass."""

    def test_eq_operator_keeps_string_value(self):
        spec = FilterSpec(field="status", operator=FilterOperator.EQ, value="active")
        assert spec.value == "active"

    def test_in_operator_splits_comma_values(self):
        spec = FilterSpec(field="status", operator=FilterOperator.IN, value="a,b,c")
        assert spec.value == ["a", "b", "c"]

    def test_in_operator_strips_whitespace(self):
        spec = FilterSpec(field="status", operator=FilterOperator.IN, value="a, b , c")
        assert spec.value == ["a", "b", "c"]

    def test_is_null_operator_converts_true(self):
        spec = FilterSpec(
            field="deleted_at", operator=FilterOperator.IS_NULL, value="true"
        )
        assert spec.value is True

    def test_is_null_operator_converts_false(self):
        spec = FilterSpec(
            field="deleted_at", operator=FilterOperator.IS_NULL, value="false"
        )
        assert spec.value is False

    def test_is_null_operator_converts_1(self):
        spec = FilterSpec(
            field="deleted_at", operator=FilterOperator.IS_NULL, value="1"
        )
        assert spec.value is True


class TestParseFilters:
    """Tests for parse_filters function."""

    def _create_mock_request(self, query_params: dict) -> MagicMock:
        request = MagicMock()
        request.query_params = query_params
        return request

    def test_parses_simple_filter(self):
        request = self._create_mock_request({"filter[status]": "active"})
        filters = parse_filters(request)

        assert len(filters) == 1
        assert filters[0].field == "status"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "active"

    def test_parses_filter_with_operator(self):
        request = self._create_mock_request({"filter[created_at][gte]": "2024-01-01"})
        filters = parse_filters(request)

        assert len(filters) == 1
        assert filters[0].field == "created_at"
        assert filters[0].operator == FilterOperator.GTE
        assert filters[0].value == "2024-01-01"

    def test_parses_multiple_filters(self):
        request = self._create_mock_request(
            {
                "filter[status]": "active",
                "filter[user_id]": "123",
            }
        )
        filters = parse_filters(request)

        assert len(filters) == 2
        fields = {f.field for f in filters}
        assert fields == {"status", "user_id"}

    def test_ignores_non_filter_params(self):
        request = self._create_mock_request(
            {
                "filter[status]": "active",
                "limit": "10",
                "offset": "0",
                "sort": "created_at:desc",
            }
        )
        filters = parse_filters(request)

        assert len(filters) == 1
        assert filters[0].field == "status"

    def test_validates_allowed_fields(self):
        request = self._create_mock_request({"filter[invalid_field]": "value"})

        with pytest.raises(HTTPException) as exc_info:
            parse_filters(request, allowed_fields={"status", "user_id"})

        assert exc_info.value.status_code == 400
        assert "Invalid filter field" in str(exc_info.value.detail)

    def test_validates_operator(self):
        request = self._create_mock_request({"filter[status][invalid_op]": "value"})

        with pytest.raises(HTTPException) as exc_info:
            parse_filters(request)

        assert exc_info.value.status_code == 400
        assert "Invalid filter operator" in str(exc_info.value.detail)

    def test_allows_all_fields_when_not_specified(self):
        request = self._create_mock_request({"filter[any_field]": "value"})
        filters = parse_filters(request)

        assert len(filters) == 1
        assert filters[0].field == "any_field"


class TestParseSort:
    """Tests for parse_sort function."""

    def test_parses_single_sort(self):
        sorts = parse_sort("created_at:desc")

        assert len(sorts) == 1
        assert sorts[0].field == "created_at"
        assert sorts[0].direction == "desc"

    def test_parses_multiple_sorts(self):
        sorts = parse_sort("name:asc,created_at:desc")

        assert len(sorts) == 2
        assert sorts[0].field == "name"
        assert sorts[0].direction == "asc"
        assert sorts[1].field == "created_at"
        assert sorts[1].direction == "desc"

    def test_returns_empty_for_none(self):
        sorts = parse_sort(None)
        assert sorts == []

    def test_returns_default_when_provided(self):
        sorts = parse_sort(None, default_sort="created_at:desc")

        assert len(sorts) == 1
        assert sorts[0].field == "created_at"
        assert sorts[0].direction == "desc"

    def test_validates_sort_format(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_sort("invalid_format")

        assert exc_info.value.status_code == 400
        assert "Invalid sort format" in str(exc_info.value.detail)

    def test_validates_allowed_fields(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_sort("invalid_field:asc", allowed_fields={"name", "created_at"})

        assert exc_info.value.status_code == 400
        assert "Invalid sort field" in str(exc_info.value.detail)

    def test_case_insensitive_direction(self):
        sorts = parse_sort("name:ASC")
        assert sorts[0].direction == "asc"


class TestGetSearchParam:
    """Tests for get_search_param function."""

    def test_returns_search_term(self):
        request = MagicMock()
        request.query_params = {"q": "search term"}

        result = get_search_param(request)
        assert result == "search term"

    def test_returns_none_when_missing(self):
        request = MagicMock()
        request.query_params = {}

        result = get_search_param(request)
        assert result is None


class TestGetPaginationParams:
    """Tests for get_pagination_params function."""

    def test_returns_defaults(self):
        request = MagicMock()
        request.query_params = {}

        limit, offset = get_pagination_params(request)

        assert limit == 50
        assert offset == 0

    def test_parses_provided_values(self):
        request = MagicMock()
        request.query_params = {"limit": "20", "offset": "40"}

        limit, offset = get_pagination_params(request)

        assert limit == 20
        assert offset == 40

    def test_validates_limit_minimum(self):
        request = MagicMock()
        request.query_params = {"limit": "0"}

        with pytest.raises(HTTPException) as exc_info:
            get_pagination_params(request)

        assert exc_info.value.status_code == 400
        assert "limit must be at least 1" in str(exc_info.value.detail)

    def test_validates_limit_maximum(self):
        request = MagicMock()
        request.query_params = {"limit": "200"}

        with pytest.raises(HTTPException) as exc_info:
            get_pagination_params(request)

        assert exc_info.value.status_code == 400
        assert "limit cannot exceed 100" in str(exc_info.value.detail)

    def test_validates_offset_non_negative(self):
        request = MagicMock()
        request.query_params = {"offset": "-1"}

        with pytest.raises(HTTPException) as exc_info:
            get_pagination_params(request)

        assert exc_info.value.status_code == 400
        assert "offset must be non-negative" in str(exc_info.value.detail)

    def test_handles_invalid_values(self):
        request = MagicMock()
        request.query_params = {"limit": "not_a_number"}

        with pytest.raises(HTTPException) as exc_info:
            get_pagination_params(request)

        assert exc_info.value.status_code == 400
        assert "Invalid pagination parameters" in str(exc_info.value.detail)

    def test_custom_defaults(self):
        request = MagicMock()
        request.query_params = {}

        limit, offset = get_pagination_params(request, default_limit=25, max_limit=50)

        assert limit == 25
        assert offset == 0
