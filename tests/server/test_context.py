import warnings
from unittest.mock import MagicMock, patch

import pytest
from mcp.types import ModelPreferences
from starlette.requests import Request

from fastmcp.server.context import Context, _parse_model_preferences
from fastmcp.server.server import FastMCP


class TestContextDeprecations:
    def test_get_http_request_deprecation_warning(self):
        """Test that using Context.get_http_request() raises a deprecation warning."""
        # Create a mock FastMCP instance
        mock_fastmcp = MagicMock()
        context = Context(fastmcp=mock_fastmcp)

        # Patch the dependency function to return a mock request
        mock_request = MagicMock(spec=Request)
        with patch(
            "fastmcp.server.dependencies.get_http_request", return_value=mock_request
        ):
            # Check that the deprecation warning is raised
            with pytest.warns(
                DeprecationWarning, match="Context.get_http_request\\(\\) is deprecated"
            ):
                request = context.get_http_request()

            # Verify the function still works and returns the request
            assert request is mock_request

    def test_get_http_request_deprecation_message(self):
        """Test that the deprecation warning has the correct message with guidance."""
        # Create a mock FastMCP instance
        mock_fastmcp = MagicMock()
        context = Context(fastmcp=mock_fastmcp)

        # Patch the dependency function to return a mock request
        mock_request = MagicMock(spec=Request)
        with patch(
            "fastmcp.server.dependencies.get_http_request", return_value=mock_request
        ):
            # Capture and check the specific warning message
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                context.get_http_request()

                assert len(w) == 1
                warning = w[0]
                assert issubclass(warning.category, DeprecationWarning)
                assert "Context.get_http_request() is deprecated" in str(
                    warning.message
                )
                assert (
                    "Use get_http_request() from fastmcp.server.dependencies instead"
                    in str(warning.message)
                )
                assert "https://gofastmcp.com/patterns/http-requests" in str(
                    warning.message
                )


@pytest.fixture
def context():
    return Context(fastmcp=FastMCP())


class TestParseModelPreferences:
    def test_parse_model_preferences_string(self, context):
        mp = _parse_model_preferences("claude-3-sonnet")
        assert isinstance(mp, ModelPreferences)
        assert mp.hints is not None
        assert mp.hints[0].name == "claude-3-sonnet"

    def test_parse_model_preferences_list(self, context):
        mp = _parse_model_preferences(["claude-3-sonnet", "claude"])
        assert isinstance(mp, ModelPreferences)
        assert mp.hints is not None
        assert [h.name for h in mp.hints] == ["claude-3-sonnet", "claude"]

    def test_parse_model_preferences_object(self, context):
        obj = ModelPreferences(hints=[])
        assert _parse_model_preferences(obj) is obj

    def test_parse_model_preferences_invalid_type(self, context):
        with pytest.raises(ValueError):
            _parse_model_preferences(model_preferences=123)  # pyright: ignore[reportArgumentType] # type: ignore[invalid-argument-type]


class TestSessionId:
    def test_session_id_with_http_headers(self, context):
        """Test that session_id returns the value from mcp-session-id header."""
        from mcp.server.lowlevel.server import request_ctx
        from mcp.shared.context import RequestContext

        mock_headers = {"mcp-session-id": "test-session-123"}

        token = request_ctx.set(
            RequestContext(  # type: ignore[arg-type]
                request_id=0,
                meta=None,
                session=MagicMock(wraps={}),
                lifespan_context=MagicMock(),
                request=MagicMock(headers=mock_headers),
            )
        )

        assert context.session_id == "test-session-123"

        request_ctx.reset(token)

    def test_session_id_without_http_headers(self, context):
        """Test that session_id returns a UUID string when no HTTP headers are available."""
        import uuid

        from mcp.server.lowlevel.server import request_ctx
        from mcp.shared.context import RequestContext

        token = request_ctx.set(
            RequestContext(  # type: ignore[arg-type]
                request_id=0,
                meta=None,
                session=MagicMock(wraps={}),
                lifespan_context=MagicMock(),
            )
        )

        assert uuid.UUID(context.session_id)

        request_ctx.reset(token)


class TestContextState:
    """Test suite for Context state functionality."""

    @pytest.mark.asyncio
    async def test_context_state(self):
        """Test that state modifications in child contexts don't affect parent."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            assert context.get_state("test1") is None
            assert context.get_state("test2") is None
            context.set_state("test1", "value")
            context.set_state("test2", 2)
            assert context.get_state("test1") == "value"
            assert context.get_state("test2") == 2
            context.set_state("test1", "new_value")
            assert context.get_state("test1") == "new_value"

    @pytest.mark.asyncio
    async def test_context_state_inheritance(self):
        """Test that child contexts inherit parent state."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context1:
            context1.set_state("key1", "key1-context1")
            context1.set_state("key2", "key2-context1")
            async with Context(fastmcp=mock_fastmcp) as context2:
                # Override one key
                context2.set_state("key1", "key1-context2")
                assert context2.get_state("key1") == "key1-context2"
                assert context1.get_state("key1") == "key1-context1"
                assert context2.get_state("key2") == "key2-context1"

                async with Context(fastmcp=mock_fastmcp) as context3:
                    # Verify state was inherited
                    assert context3.get_state("key1") == "key1-context2"
                    assert context3.get_state("key2") == "key2-context1"

                    # Add a new key and verify parents were not affected
                    context3.set_state("key-context3-only", 1)
                    assert context1.get_state("key-context3-only") is None
                    assert context2.get_state("key-context3-only") is None
                    assert context3.get_state("key-context3-only") == 1

            assert context1.get_state("key1") == "key1-context1"
            assert context1.get_state("key-context3-only") is None


class TestContextSnapshots:
    """Test suite for Context snapshot functionality."""

    @pytest.mark.asyncio
    async def test_create_snapshot_basic(self):
        """Test basic snapshot creation."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Set up some state
            context.set_state("user", "alice")
            context.set_state("theme", "dark")
            
            # Create snapshot
            result = context.create_snapshot("test_snapshot")
            assert result == "State snapshot 'test_snapshot' created with 2 items"
            
            # Verify snapshot exists in list
            snapshots = context.list_snapshots()
            assert "test_snapshot" in snapshots

    @pytest.mark.asyncio
    async def test_create_snapshot_overwrite(self):
        """Test that creating a snapshot with same name overwrites."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Create initial snapshot
            context.set_state("count", 1)
            context.create_snapshot("counter")
            
            # Modify state and overwrite snapshot
            context.set_state("count", 2)
            result = context.create_snapshot("counter")
            assert result == "State snapshot 'counter' created with 1 items"
            
            # Verify only one snapshot exists
            snapshots = context.list_snapshots()
            assert len(snapshots) == 1
            assert "counter" in snapshots
            
            # Verify snapshot has new value
            snapshot_data = context.get_snapshot("counter")
            assert snapshot_data["count"] == 2

    @pytest.mark.asyncio
    async def test_list_snapshots_empty(self):
        """Test listing snapshots when none exist."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            snapshots = context.list_snapshots()
            assert snapshots == []

    @pytest.mark.asyncio
    async def test_list_snapshots_multiple(self):
        """Test listing multiple snapshots."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            context.set_state("data", "test")
            context.create_snapshot("snap1")
            context.create_snapshot("snap2")
            context.create_snapshot("snap3")
            
            snapshots = context.list_snapshots()
            assert len(snapshots) == 3
            assert set(snapshots) == {"snap1", "snap2", "snap3"}

    @pytest.mark.asyncio
    async def test_get_snapshot_success(self):
        """Test getting snapshot data."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Set up state and create snapshot
            context.set_state("user", "bob")
            context.set_state("settings", {"theme": "light", "lang": "en"})
            context.create_snapshot("user_setup")
            
            # Get snapshot data
            snapshot_data = context.get_snapshot("user_setup")
            expected = {"user": "bob", "settings": {"theme": "light", "lang": "en"}}
            assert snapshot_data == expected
            
            # Verify it's a deep copy (modifying returned data doesn't affect snapshot)
            snapshot_data["user"] = "charlie"
            snapshot_data["settings"]["theme"] = "dark"
            
            # Original snapshot should be unchanged
            original_data = context.get_snapshot("user_setup")
            assert original_data["user"] == "bob"
            assert original_data["settings"]["theme"] == "light"

    @pytest.mark.asyncio
    async def test_get_snapshot_not_found(self):
        """Test getting non-existent snapshot raises KeyError."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            with pytest.raises(KeyError, match="Snapshot 'missing' not found"):
                context.get_snapshot("missing")

    @pytest.mark.asyncio
    async def test_restore_snapshot_success(self):
        """Test restoring state from snapshot."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Set up initial state and create snapshot
            context.set_state("config", "original")
            context.set_state("count", 1)
            context.create_snapshot("backup")
            
            # Modify state
            context.set_state("config", "modified")
            context.set_state("count", 10)
            context.set_state("new_key", "added")
            
            # Restore from snapshot
            result = context.restore_snapshot("backup")
            assert result == "State restored from snapshot 'backup' with 2 items"
            
            # Verify state was restored
            assert context.get_state("config") == "original"
            assert context.get_state("count") == 1
            assert context.get_state("new_key") is None  # Should be removed

    @pytest.mark.asyncio
    async def test_restore_snapshot_not_found(self):
        """Test restoring from non-existent snapshot raises KeyError."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            with pytest.raises(KeyError, match="Snapshot 'missing' not found"):
                context.restore_snapshot("missing")

    @pytest.mark.asyncio
    async def test_delete_snapshot_success(self):
        """Test deleting a snapshot."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Create snapshots
            context.set_state("data", "test")
            context.create_snapshot("snap1")
            context.create_snapshot("snap2")
            
            # Verify both exist
            snapshots = context.list_snapshots()
            assert len(snapshots) == 2
            
            # Delete one
            result = context.delete_snapshot("snap1")
            assert result == "Snapshot 'snap1' deleted"
            
            # Verify only one remains
            snapshots = context.list_snapshots()
            assert snapshots == ["snap2"]

    @pytest.mark.asyncio
    async def test_delete_snapshot_not_found(self):
        """Test deleting non-existent snapshot raises KeyError."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            with pytest.raises(KeyError, match="Snapshot 'missing' not found"):
                context.delete_snapshot("missing")

    @pytest.mark.asyncio
    async def test_get_snapshot_diff_comprehensive(self):
        """Test comprehensive snapshot diff functionality."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Set up initial state
            context.set_state("unchanged", "same")
            context.set_state("to_modify", "old_value")
            context.set_state("to_remove", "will_be_removed")
            context.create_snapshot("before")
            
            # Modify state
            context.set_state("to_modify", "new_value")  # Modified
            context.set_state("to_add", "added_value")    # Added
            del context._state["to_remove"]               # Removed
            # unchanged remains the same
            context.create_snapshot("after")
            
            # Test diff
            diff = context.get_snapshot_diff("before", "after")
            
            expected = {
                "added": {"to_add": "added_value"},
                "removed": {"to_remove": "will_be_removed"},
                "modified": {"to_modify": {"old": "old_value", "new": "new_value"}},
                "unchanged": {"unchanged": "same"}
            }
            assert diff == expected

    @pytest.mark.asyncio
    async def test_get_snapshot_diff_identical_snapshots(self):
        """Test diff between identical snapshots."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            context.set_state("key1", "value1")
            context.set_state("key2", {"nested": "data"})
            context.create_snapshot("snap1")
            context.create_snapshot("snap2")  # Same state
            
            diff = context.get_snapshot_diff("snap1", "snap2")
            
            expected = {
                "added": {},
                "removed": {},
                "modified": {},
                "unchanged": {"key1": "value1", "key2": {"nested": "data"}}
            }
            assert diff == expected

    @pytest.mark.asyncio
    async def test_get_snapshot_diff_empty_snapshots(self):
        """Test diff between empty snapshots."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Create empty snapshots
            context.create_snapshot("empty1")
            context.create_snapshot("empty2")
            
            diff = context.get_snapshot_diff("empty1", "empty2")
            
            expected = {
                "added": {},
                "removed": {},
                "modified": {},
                "unchanged": {}
            }
            assert diff == expected

    @pytest.mark.asyncio
    async def test_get_snapshot_diff_not_found(self):
        """Test diff with non-existent snapshots raises KeyError."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            context.create_snapshot("exists")
            
            # Test first snapshot missing
            with pytest.raises(KeyError, match="Snapshot 'missing1' not found"):
                context.get_snapshot_diff("missing1", "exists")
                
            # Test second snapshot missing
            with pytest.raises(KeyError, match="Snapshot 'missing2' not found"):
                context.get_snapshot_diff("exists", "missing2")

    @pytest.mark.asyncio
    async def test_snapshot_inheritance_in_nested_contexts(self):
        """Test that snapshots are inherited in nested contexts."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context1:
            # Create snapshots in parent context
            context1.set_state("parent_data", "value1")
            context1.create_snapshot("parent_snapshot")
            
            async with Context(fastmcp=mock_fastmcp) as context2:
                # Child should inherit parent snapshots
                snapshots = context2.list_snapshots()
                assert "parent_snapshot" in snapshots
                
                # Child should be able to access parent snapshot
                snapshot_data = context2.get_snapshot("parent_snapshot")
                assert snapshot_data["parent_data"] == "value1"
                
                # Child can create its own snapshots
                context2.set_state("child_data", "value2")
                context2.create_snapshot("child_snapshot")
                
                # Child should see both snapshots
                child_snapshots = context2.list_snapshots()
                assert len(child_snapshots) == 2
                assert set(child_snapshots) == {"parent_snapshot", "child_snapshot"}
                
                # Modify parent snapshot in child (should not affect parent)
                context2.set_state("modified", "in_child")
                context2.create_snapshot("parent_snapshot")  # Overwrite
                
            # Parent should still have original snapshot
            parent_snapshots = context1.list_snapshots()
            assert "parent_snapshot" in parent_snapshots
            assert "child_snapshot" not in parent_snapshots  # Child snapshots don't bubble up
            
            # Parent snapshot should be unchanged
            parent_snapshot_data = context1.get_snapshot("parent_snapshot")
            assert "modified" not in parent_snapshot_data
            assert parent_snapshot_data["parent_data"] == "value1"

    @pytest.mark.asyncio
    async def test_snapshot_with_complex_data_structures(self):
        """Test snapshots work correctly with complex nested data structures."""
        mock_fastmcp = MagicMock()

        async with Context(fastmcp=mock_fastmcp) as context:
            # Set up complex state
            complex_data = {
                "users": [
                    {"id": 1, "name": "Alice", "settings": {"theme": "dark"}},
                    {"id": 2, "name": "Bob", "settings": {"theme": "light"}}
                ],
                "config": {
                    "database": {"host": "localhost", "port": 5432},
                    "features": {"feature_a": True, "feature_b": False}
                }
            }
            context.set_state("app_data", complex_data)
            context.create_snapshot("complex")
            
            # Modify the state
            context.get_state("app_data")["users"][0]["name"] = "Alice Updated"
            
            # Restore snapshot
            context.restore_snapshot("complex")
            
            # Verify original data is restored (not the modified version)
            restored_data = context.get_state("app_data")
            assert restored_data["users"][0]["name"] == "Alice"  # Original value
            assert restored_data["config"]["database"]["host"] == "localhost"
