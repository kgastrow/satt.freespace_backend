"""
Tests for Query Builder utilities.
"""

from sqlalchemy import Column, DateTime, Integer, String, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_search,
    apply_sort,
)
from src.core.query_params import FilterOperator, FilterSpec, SortSpec


class Base(DeclarativeBase):
    pass


class MockModel(Base):
    __tablename__ = "mock_model"

    id = Column(PGUUID(as_uuid=True), primary_key=True)
    name = Column(String)
    status = Column(String)
    count = Column(Integer)
    created_at = Column(DateTime)
    user_id = Column(PGUUID(as_uuid=True))


class TestApplyFilters:
    """Tests for apply_filters function."""

    def test_applies_eq_filter(self):
        query = select(MockModel)
        filters = [
            FilterSpec(field="status", operator=FilterOperator.EQ, value="active")
        ]

        result = apply_filters(query, MockModel, filters)

        # Verify the query has a WHERE clause
        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.status =" in compiled

    def test_applies_ne_filter(self):
        query = select(MockModel)
        filters = [
            FilterSpec(field="status", operator=FilterOperator.NE, value="deleted")
        ]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.status !=" in compiled or "mock_model.status <>" in compiled

    def test_applies_gt_filter(self):
        query = select(MockModel)
        filters = [FilterSpec(field="count", operator=FilterOperator.GT, value="10")]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.count >" in compiled

    def test_applies_gte_filter(self):
        query = select(MockModel)
        filters = [FilterSpec(field="count", operator=FilterOperator.GTE, value="10")]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.count >=" in compiled

    def test_applies_lt_filter(self):
        query = select(MockModel)
        filters = [FilterSpec(field="count", operator=FilterOperator.LT, value="10")]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.count <" in compiled

    def test_applies_lte_filter(self):
        query = select(MockModel)
        filters = [FilterSpec(field="count", operator=FilterOperator.LTE, value="10")]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.count <=" in compiled

    def test_applies_in_filter(self):
        query = select(MockModel)
        filters = [
            FilterSpec(field="status", operator=FilterOperator.IN, value="a,b,c")
        ]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.status IN" in compiled

    def test_applies_contains_filter(self):
        query = select(MockModel)
        filters = [
            FilterSpec(field="name", operator=FilterOperator.CONTAINS, value="john")
        ]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "lower(mock_model.name) LIKE" in compiled
        assert "%john%" in compiled

    def test_applies_is_null_true_filter(self):
        query = select(MockModel)
        filters = [
            FilterSpec(
                field="created_at", operator=FilterOperator.IS_NULL, value="true"
            )
        ]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.created_at IS NULL" in compiled

    def test_applies_is_null_false_filter(self):
        query = select(MockModel)
        filters = [
            FilterSpec(
                field="created_at", operator=FilterOperator.IS_NULL, value="false"
            )
        ]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.created_at IS NOT NULL" in compiled

    def test_applies_multiple_filters(self):
        query = select(MockModel)
        filters = [
            FilterSpec(field="status", operator=FilterOperator.EQ, value="active"),
            FilterSpec(field="count", operator=FilterOperator.GTE, value="5"),
        ]

        result = apply_filters(query, MockModel, filters)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.status =" in compiled
        assert "mock_model.count >=" in compiled

    def test_uses_field_mapping(self):
        query = select(MockModel)
        filters = [FilterSpec(field="type", operator=FilterOperator.EQ, value="admin")]
        field_mapping = {"type": "status"}

        result = apply_filters(query, MockModel, filters, field_mapping)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.status =" in compiled

    def test_skips_unknown_fields(self):
        query = select(MockModel)
        filters = [
            FilterSpec(field="unknown_field", operator=FilterOperator.EQ, value="value")
        ]

        result = apply_filters(query, MockModel, filters)

        # Should return query unchanged (no WHERE clause added)
        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "WHERE" not in compiled

    def test_converts_uuid_values(self):
        query = select(MockModel)
        test_uuid = "12345678-1234-5678-1234-567812345678"
        filters = [
            FilterSpec(field="user_id", operator=FilterOperator.EQ, value=test_uuid)
        ]

        result = apply_filters(query, MockModel, filters)

        # Query should compile without error
        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "mock_model.user_id" in compiled


class TestApplySort:
    """Tests for apply_sort function."""

    def test_applies_asc_sort(self):
        query = select(MockModel)
        sorts = [SortSpec(field="name", direction="asc")]

        result = apply_sort(query, MockModel, sorts)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY mock_model.name ASC" in compiled

    def test_applies_desc_sort(self):
        query = select(MockModel)
        sorts = [SortSpec(field="created_at", direction="desc")]

        result = apply_sort(query, MockModel, sorts)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY mock_model.created_at DESC" in compiled

    def test_applies_multiple_sorts(self):
        query = select(MockModel)
        sorts = [
            SortSpec(field="status", direction="asc"),
            SortSpec(field="created_at", direction="desc"),
        ]

        result = apply_sort(query, MockModel, sorts)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY" in compiled
        assert "mock_model.status ASC" in compiled
        assert "mock_model.created_at DESC" in compiled

    def test_uses_default_sort_when_empty(self):
        query = select(MockModel)
        sorts = []

        result = apply_sort(
            query,
            MockModel,
            sorts,
            default_sort_field="created_at",
            default_sort_direction="desc",
        )

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY mock_model.created_at DESC" in compiled

    def test_uses_field_mapping(self):
        query = select(MockModel)
        sorts = [SortSpec(field="title", direction="asc")]
        field_mapping = {"title": "name"}

        result = apply_sort(query, MockModel, sorts, field_mapping)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY mock_model.name ASC" in compiled

    def test_skips_unknown_fields(self):
        query = select(MockModel)
        sorts = [SortSpec(field="unknown_field", direction="asc")]

        result = apply_sort(query, MockModel, sorts)

        # Should return query unchanged (no ORDER BY clause added)
        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY" not in compiled


class TestApplyPagination:
    """Tests for apply_pagination function."""

    def test_applies_limit_and_offset(self):
        query = select(MockModel)

        result = apply_pagination(query, limit=20, offset=40)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 20" in compiled
        assert "OFFSET 40" in compiled

    def test_applies_zero_offset(self):
        query = select(MockModel)

        result = apply_pagination(query, limit=10, offset=0)

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10" in compiled
        assert "OFFSET 0" in compiled


class TestApplySearch:
    """Tests for apply_search function."""

    def test_applies_search_to_single_field(self):
        query = select(MockModel)

        result = apply_search(query, MockModel, "john", ["name"])

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "lower(mock_model.name) LIKE" in compiled
        assert "%john%" in compiled

    def test_applies_search_to_multiple_fields(self):
        query = select(MockModel)

        result = apply_search(query, MockModel, "test", ["name", "status"])

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "lower(mock_model.name) LIKE" in compiled
        assert "lower(mock_model.status) LIKE" in compiled
        assert "OR" in compiled

    def test_returns_unchanged_for_empty_search(self):
        query = select(MockModel)

        result = apply_search(query, MockModel, "", ["name"])

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "WHERE" not in compiled

    def test_returns_unchanged_for_none_search(self):
        query = select(MockModel)

        result = apply_search(query, MockModel, None, ["name"])

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "WHERE" not in compiled

    def test_returns_unchanged_for_empty_fields(self):
        query = select(MockModel)

        result = apply_search(query, MockModel, "test", [])

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        assert "WHERE" not in compiled

    def test_skips_unknown_fields(self):
        query = select(MockModel)

        result = apply_search(query, MockModel, "test", ["name", "unknown_field"])

        compiled = str(result.compile(compile_kwargs={"literal_binds": True}))
        # Should only search in known 'name' field
        assert "lower(mock_model.name) LIKE" in compiled
        assert "unknown_field" not in compiled
