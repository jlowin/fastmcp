"""Tests for server dependency handling in install command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastmcp.cli.install.install import Client, install


class TestServerDependencies:
    """Test that server dependencies are properly merged and passed to integrations."""

    @patch("fastmcp.cli.install.install.install_claude_code")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_merges_server_dependencies_claude_code(
        self, mock_parse, mock_import, mock_install_claude_code
    ):
        """Should merge server dependencies with provided packages for Claude Code."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_server = MagicMock()
        mock_server.name = "Test Server"
        mock_server.dependencies = ["pandas", "requests"]
        mock_import.return_value = mock_server
        mock_install_claude_code.return_value = True

        # Call install with additional packages
        install(
            client=Client.CLAUDE_CODE,
            server_spec="server.py",
            with_packages=["numpy", "requests"],  # requests should be deduplicated
        )

        # Verify merged dependencies were passed
        mock_install_claude_code.assert_called_once()
        call_kwargs = mock_install_claude_code.call_args.kwargs

        # Should contain both server dependencies and provided packages, deduplicated
        expected_packages = {"pandas", "requests", "numpy"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages

    @patch("fastmcp.cli.install.install.install_claude_desktop")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_merges_server_dependencies_claude_desktop(
        self, mock_parse, mock_import, mock_install_claude_desktop
    ):
        """Should merge server dependencies with provided packages for Claude Desktop."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_server = MagicMock()
        mock_server.name = "Test Server"
        mock_server.dependencies = ["pandas", "requests"]
        mock_import.return_value = mock_server
        mock_install_claude_desktop.return_value = True

        # Call install with additional packages
        install(
            client=Client.CLAUDE_DESKTOP,
            server_spec="server.py",
            with_packages=["numpy"],
        )

        # Verify merged dependencies were passed
        mock_install_claude_desktop.assert_called_once()
        call_kwargs = mock_install_claude_desktop.call_args.kwargs

        # Should contain both server dependencies and provided packages
        expected_packages = {"pandas", "requests", "numpy"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages

    @patch("fastmcp.cli.install.install.install_cursor")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_merges_server_dependencies_cursor(
        self, mock_parse, mock_import, mock_install_cursor
    ):
        """Should merge server dependencies with provided packages for Cursor."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_server = MagicMock()
        mock_server.name = "Test Server"
        mock_server.dependencies = ["pandas", "requests"]
        mock_import.return_value = mock_server
        mock_install_cursor.return_value = True

        # Call install
        install(
            client=Client.CURSOR,
            server_spec="server.py",
        )

        # Verify server dependencies were passed
        mock_install_cursor.assert_called_once()
        call_kwargs = mock_install_cursor.call_args.kwargs

        # Should contain server dependencies
        expected_packages = {"pandas", "requests"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages

    @patch("fastmcp.cli.install.install.install_claude_code")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_handles_server_without_dependencies(
        self, mock_parse, mock_import, mock_install_claude_code
    ):
        """Should handle servers without dependencies attribute."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_server = MagicMock()
        mock_server.name = "Test Server"
        # No dependencies attribute
        del mock_server.dependencies
        mock_import.return_value = mock_server
        mock_install_claude_code.return_value = True

        # Call install with packages
        install(
            client=Client.CLAUDE_CODE,
            server_spec="server.py",
            with_packages=["numpy"],
        )

        # Verify only provided packages were passed
        mock_install_claude_code.assert_called_once()
        call_kwargs = mock_install_claude_code.call_args.kwargs

        expected_packages = {"numpy"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages

    @patch("fastmcp.cli.install.install.install_claude_code")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_handles_server_with_empty_dependencies(
        self, mock_parse, mock_import, mock_install_claude_code
    ):
        """Should handle servers with empty dependencies list."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_server = MagicMock()
        mock_server.name = "Test Server"
        mock_server.dependencies = []  # Empty list
        mock_import.return_value = mock_server
        mock_install_claude_code.return_value = True

        # Call install with packages
        install(
            client=Client.CLAUDE_CODE,
            server_spec="server.py",
            with_packages=["numpy"],
        )

        # Verify only provided packages were passed
        mock_install_claude_code.assert_called_once()
        call_kwargs = mock_install_claude_code.call_args.kwargs

        expected_packages = {"numpy"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages

    @patch("fastmcp.cli.install.install.install_claude_code")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_deduplicates_dependencies(
        self, mock_parse, mock_import, mock_install_claude_code
    ):
        """Should deduplicate dependencies between server and provided packages."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_server = MagicMock()
        mock_server.name = "Test Server"
        mock_server.dependencies = ["pandas", "requests", "numpy"]
        mock_import.return_value = mock_server
        mock_install_claude_code.return_value = True

        # Call install with overlapping packages
        install(
            client=Client.CLAUDE_CODE,
            server_spec="server.py",
            with_packages=["numpy", "requests", "matplotlib"],  # Some overlap
        )

        # Verify dependencies were deduplicated
        mock_install_claude_code.assert_called_once()
        call_kwargs = mock_install_claude_code.call_args.kwargs

        # Should contain unique packages only
        expected_packages = {"pandas", "requests", "numpy", "matplotlib"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages

        # Should not have duplicates
        actual_packages_list = call_kwargs["with_packages"]
        assert len(actual_packages_list) == len(set(actual_packages_list))

    @patch("fastmcp.cli.install.install.install_claude_code")
    @patch("fastmcp.cli.install.install.import_server")
    @patch("fastmcp.cli.install.install.parse_file_path")
    def test_handles_import_failure_gracefully(
        self, mock_parse, mock_import, mock_install_claude_code
    ):
        """Should handle server import failure and still install with provided packages."""
        # Setup mocks
        mock_parse.return_value = (Path("server.py"), None)
        mock_import.side_effect = ImportError("Missing dependency")
        mock_install_claude_code.return_value = True

        # Call install with packages
        install(
            client=Client.CLAUDE_CODE,
            server_spec="server.py",
            with_packages=["numpy"],
        )

        # Should still call install with provided packages
        mock_install_claude_code.assert_called_once()
        call_kwargs = mock_install_claude_code.call_args.kwargs

        expected_packages = {"numpy"}
        actual_packages = set(call_kwargs["with_packages"])
        assert actual_packages == expected_packages
