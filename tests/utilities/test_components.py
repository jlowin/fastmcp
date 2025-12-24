"""Tests for fastmcp.utilities.components module."""

import pytest
from pydantic import ValidationError

from fastmcp.utilities.components import (
    FastMCPComponent,
    FastMCPMeta,
    _convert_set_default_none,
)


class TestConvertSetDefaultNone:
    """Tests for the _convert_set_default_none helper function."""

    def test_none_returns_empty_set(self):
        """Test that None returns an empty set."""
        result = _convert_set_default_none(None)
        assert result == set()

    def test_set_returns_same_set(self):
        """Test that a set returns the same set."""
        test_set = {"tag1", "tag2"}
        result = _convert_set_default_none(test_set)
        assert result == test_set

    def test_list_converts_to_set(self):
        """Test that a list converts to a set."""
        test_list = ["tag1", "tag2", "tag1"]  # Duplicate to test deduplication
        result = _convert_set_default_none(test_list)
        assert result == {"tag1", "tag2"}

    def test_tuple_converts_to_set(self):
        """Test that a tuple converts to a set."""
        test_tuple = ("tag1", "tag2")
        result = _convert_set_default_none(test_tuple)
        assert result == {"tag1", "tag2"}


class TestFastMCPComponent:
    """Tests for the FastMCPComponent class."""

    @pytest.fixture
    def basic_component(self):
        """Create a basic component for testing."""
        return FastMCPComponent(
            name="test_component",
            title="Test Component",
            description="A test component",
            tags={"test", "component"},
        )

    def test_initialization_with_minimal_params(self):
        """Test component initialization with minimal parameters."""
        component = FastMCPComponent(name="minimal")
        assert component.name == "minimal"
        assert component.title is None
        assert component.description is None
        assert component.tags == set()
        assert component.meta is None

    def test_initialization_with_all_params(self):
        """Test component initialization with all parameters."""
        meta = {"custom": "value"}
        component = FastMCPComponent(
            name="full",
            title="Full Component",
            description="A fully configured component",
            tags={"tag1", "tag2"},
            meta=meta,
        )
        assert component.name == "full"
        assert component.title == "Full Component"
        assert component.description == "A fully configured component"
        assert component.tags == {"tag1", "tag2"}
        assert component.meta == meta

    def test_key_property_without_custom_key(self, basic_component):
        """Test that key property returns name when no custom key is set."""
        assert basic_component.key == "test_component"

    def test_get_meta_without_fastmcp_meta(self, basic_component):
        """Test get_meta without including fastmcp meta."""
        basic_component.meta = {"custom": "data"}
        result = basic_component.get_meta(include_fastmcp_meta=False)
        assert result == {"custom": "data"}
        assert "_fastmcp" not in result

    def test_get_meta_with_fastmcp_meta(self, basic_component):
        """Test get_meta including fastmcp meta."""
        basic_component.meta = {"custom": "data"}
        basic_component.tags = {"tag2", "tag1"}  # Unordered to test sorting
        result = basic_component.get_meta(include_fastmcp_meta=True)
        assert result["custom"] == "data"
        assert "_fastmcp" in result
        assert result["_fastmcp"]["tags"] == ["tag1", "tag2"]  # Should be sorted

    def test_get_meta_preserves_existing_fastmcp_meta(self):
        """Test that get_meta preserves existing _fastmcp meta."""
        component = FastMCPComponent(
            name="test",
            meta={"_fastmcp": {"existing": "value"}},
            tags={"new_tag"},
        )
        result = component.get_meta(include_fastmcp_meta=True)
        assert result is not None
        assert result["_fastmcp"]["existing"] == "value"
        assert result["_fastmcp"]["tags"] == ["new_tag"]

    def test_get_meta_returns_none_when_empty(self):
        """Test that get_meta returns None when no meta and fastmcp_meta is False."""
        component = FastMCPComponent(name="test")
        result = component.get_meta(include_fastmcp_meta=False)
        assert result is None

    def test_equality_same_components(self):
        """Test that identical components are equal."""
        comp1 = FastMCPComponent(name="test", description="desc")
        comp2 = FastMCPComponent(name="test", description="desc")
        assert comp1 == comp2

    def test_equality_different_components(self):
        """Test that different components are not equal."""
        comp1 = FastMCPComponent(name="test1")
        comp2 = FastMCPComponent(name="test2")
        assert comp1 != comp2

    def test_equality_different_types(self, basic_component):
        """Test that component is not equal to other types."""
        assert basic_component != "not a component"
        assert basic_component != 123
        assert basic_component is not None

    def test_repr(self, basic_component):
        """Test string representation of component."""
        repr_str = repr(basic_component)
        assert "FastMCPComponent" in repr_str
        assert "name='test_component'" in repr_str
        assert "title='Test Component'" in repr_str
        assert "description='A test component'" in repr_str

    def test_copy_method(self, basic_component):
        """Test copy method creates an independent copy."""
        copy = basic_component.copy()
        assert copy == basic_component
        assert copy is not basic_component

        # Modify copy and ensure original is unchanged
        copy.name = "modified"
        assert basic_component.name == "test_component"

    def test_tags_deduplication(self):
        """Test that tags are deduplicated when passed as a sequence."""
        component = FastMCPComponent(
            name="test",
            tags=["tag1", "tag2", "tag1", "tag2"],  # type: ignore[arg-type]
        )
        assert component.tags == {"tag1", "tag2"}

    def test_validation_error_for_invalid_data(self):
        """Test that validation errors are raised for invalid data."""
        with pytest.raises(ValidationError):
            FastMCPComponent()  # type: ignore[call-arg]

    def test_extra_fields_forbidden(self):
        """Test that extra fields are not allowed."""
        with pytest.raises(ValidationError) as exc_info:
            FastMCPComponent(name="test", unknown_field="value")  # type: ignore[call-arg]  # Intentionally passing invalid field for test
        assert "Extra inputs are not permitted" in str(exc_info.value)


class TestComponentEnableDisable:
    """Tests for the enable/disable methods raising NotImplementedError."""

    def test_enable_raises_not_implemented_error(self):
        """Test that enable raises NotImplementedError with migration guidance."""
        component = FastMCPComponent(name="test")
        with pytest.raises(NotImplementedError) as exc_info:
            component.enable()
        assert "removed in FastMCP 3.0" in str(exc_info.value)
        assert "server.enable" in str(exc_info.value)

    def test_disable_raises_not_implemented_error(self):
        """Test that disable raises NotImplementedError with migration guidance."""
        component = FastMCPComponent(name="test")
        with pytest.raises(NotImplementedError) as exc_info:
            component.disable()
        assert "removed in FastMCP 3.0" in str(exc_info.value)
        assert "server.disable" in str(exc_info.value)


class TestFastMCPMeta:
    """Tests for the FastMCPMeta TypedDict."""

    def test_fastmcp_meta_structure(self):
        """Test that FastMCPMeta has the expected structure."""
        meta: FastMCPMeta = {"tags": ["tag1", "tag2"]}
        assert meta["tags"] == ["tag1", "tag2"]

    def test_fastmcp_meta_optional_fields(self):
        """Test that FastMCPMeta fields are optional."""
        meta: FastMCPMeta = {}
        assert "tags" not in meta  # Should be optional


class TestEdgeCasesAndIntegration:
    """Tests for edge cases and integration scenarios."""

    def test_empty_tags_conversion(self):
        """Test that empty tags are handled correctly."""
        component = FastMCPComponent(name="test", tags=set())
        assert component.tags == set()

    def test_tags_with_none_values(self):
        """Test tags behavior with various input types."""
        # Test with None (through validator)
        component = FastMCPComponent(name="test")
        assert component.tags == set()

    def test_meta_mutation_affects_original(self):
        """Test that get_meta returns a reference to the original meta."""
        component = FastMCPComponent(name="test", meta={"key": "value"})
        meta = component.get_meta(include_fastmcp_meta=False)
        assert meta is not None
        meta["key"] = "modified"
        assert component.meta is not None
        assert component.meta["key"] == "modified"  # Original is modified

        # This is the actual behavior - get_meta returns a reference

    def test_component_with_complex_meta(self):
        """Test component with nested meta structures."""
        complex_meta = {
            "nested": {"level1": {"level2": "value"}},
            "list": [1, 2, 3],
            "bool": True,
        }
        component = FastMCPComponent(name="test", meta=complex_meta)
        assert component.meta == complex_meta

    def test_model_copy_preserves_all_attributes(self):
        """Test that model_copy preserves all component attributes."""
        component = FastMCPComponent(
            name="test",
            title="Title",
            description="Description",
            tags={"tag1", "tag2"},
            meta={"key": "value"},
        )
        new_component = component.model_copy()

        assert new_component.name == component.name
        assert new_component.title == component.title
        assert new_component.description == component.description
        assert new_component.tags == component.tags
        assert new_component.meta == component.meta
        assert new_component.key == component.key

    def test_model_copy_with_update(self):
        """Test that model_copy works with update dict."""
        component = FastMCPComponent(
            name="test",
            title="Original Title",
            description="Original Description",
            tags={"tag1"},
        )

        # Test with update (including name which affects .key)
        updated_component = component.model_copy(
            update={
                "name": "new_name",
                "title": "New Title",
                "description": "New Description",
            },
        )

        assert updated_component.name == "new_name"  # Updated
        assert updated_component.title == "New Title"  # Updated
        assert updated_component.description == "New Description"  # Updated
        assert updated_component.tags == {"tag1"}  # Not in update, unchanged
        assert updated_component.key == "new_name"  # .key is computed from name

        # Original should be unchanged
        assert component.name == "test"
        assert component.title == "Original Title"
        assert component.description == "Original Description"
        assert component.key == "test"  # Uses name as key

    def test_model_copy_deep_parameter(self):
        """Test that model_copy respects the deep parameter."""
        nested_dict = {"nested": {"value": 1}}
        component = FastMCPComponent(name="test", meta=nested_dict)

        # Shallow copy (default)
        shallow_copy = component.model_copy()
        assert shallow_copy.meta is not None
        assert component.meta is not None
        shallow_copy.meta["nested"]["value"] = 2
        assert component.meta["nested"]["value"] == 2  # Original affected

        # Deep copy
        component.meta["nested"]["value"] = 1  # Reset
        deep_copy = component.model_copy(deep=True)
        assert deep_copy.meta is not None
        deep_copy.meta["nested"]["value"] = 3
        assert component.meta["nested"]["value"] == 1  # Original unaffected
