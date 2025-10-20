"""Test that deprecated provider imports still work.

This test file verifies that the old provider class names (without DCR suffix)
can still be imported and are subclasses of the new DCR providers.
"""


class TestDeprecatedProviderImports:
    """Test that deprecated provider names can be imported and are subclasses of DCR providers."""

    def test_github_provider_import(self):
        """Test that GitHubProvider can be imported and is a GitHubDCRProvider subclass."""
        from fastmcp.server.auth.providers.github import (
            GitHubDCRProvider,
            GitHubProvider,
        )

        assert GitHubProvider is not None
        assert issubclass(GitHubProvider, GitHubDCRProvider)

    def test_google_provider_import(self):
        """Test that GoogleProvider can be imported and is a GoogleDCRProvider subclass."""
        from fastmcp.server.auth.providers.google import (
            GoogleDCRProvider,
            GoogleProvider,
        )

        assert GoogleProvider is not None
        assert issubclass(GoogleProvider, GoogleDCRProvider)

    def test_azure_provider_import(self):
        """Test that AzureProvider can be imported and is an AzureDCRProvider subclass."""
        from fastmcp.server.auth.providers.azure import AzureDCRProvider, AzureProvider

        assert AzureProvider is not None
        assert issubclass(AzureProvider, AzureDCRProvider)

    def test_workos_provider_import(self):
        """Test that WorkOSProvider can be imported and is a WorkOSDCRProvider subclass."""
        from fastmcp.server.auth.providers.workos import (
            WorkOSDCRProvider,
            WorkOSProvider,
        )

        assert WorkOSProvider is not None
        assert issubclass(WorkOSProvider, WorkOSDCRProvider)

    def test_auth0_provider_import(self):
        """Test that Auth0Provider can be imported and is an Auth0DCRProvider subclass."""
        from fastmcp.server.auth.providers.auth0 import Auth0DCRProvider, Auth0Provider

        assert Auth0Provider is not None
        assert issubclass(Auth0Provider, Auth0DCRProvider)

    def test_aws_cognito_provider_import(self):
        """Test that AWSCognitoProvider can be imported and is an AWSCognitoDCRProvider subclass."""
        from fastmcp.server.auth.providers.aws import (
            AWSCognitoDCRProvider,
            AWSCognitoProvider,
        )

        assert AWSCognitoProvider is not None
        assert issubclass(AWSCognitoProvider, AWSCognitoDCRProvider)
