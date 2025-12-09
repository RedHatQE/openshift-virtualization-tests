# Generated using Claude cli

"""Unit tests for cluster module"""

from unittest.mock import MagicMock, patch

from utilities.cluster import cache_admin_client


class TestCacheAdminClient:
    """Test cases for cache_admin_client function"""

    @patch("utilities.cluster.get_client")
    def test_cache_admin_client_returns_client(self, mock_get_client):
        """Test that cache_admin_client returns a DynamicClient"""
        # Clear the cache before testing
        cache_admin_client.cache_clear()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        result = cache_admin_client()

        assert result == mock_client
        mock_get_client.assert_called_once()

    @patch("utilities.cluster.get_client")
    def test_cache_admin_client_caches_result(self, mock_get_client):
        """Test that cache_admin_client caches the client on repeated calls"""
        # Clear the cache before testing
        cache_admin_client.cache_clear()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Call multiple times
        result1 = cache_admin_client()
        result2 = cache_admin_client()
        result3 = cache_admin_client()

        # All results should be the same cached object
        assert result1 is result2
        assert result2 is result3
        # get_client should only be called once due to caching
        mock_get_client.assert_called_once()

    @patch("utilities.cluster.get_client")
    def test_cache_admin_client_cache_clear(self, mock_get_client):
        """Test that cache can be cleared and get_client is called again"""
        # Clear the cache before testing
        cache_admin_client.cache_clear()

        mock_client1 = MagicMock()
        mock_client2 = MagicMock()
        mock_get_client.side_effect = [mock_client1, mock_client2]

        # First call
        result1 = cache_admin_client()
        assert result1 == mock_client1

        # Clear cache
        cache_admin_client.cache_clear()

        # Second call should get new client
        result2 = cache_admin_client()
        assert result2 == mock_client2

        # get_client should be called twice
        assert mock_get_client.call_count == 2

    @patch("utilities.cluster.get_client")
    def test_cache_admin_client_cache_info(self, mock_get_client):
        """Test that cache_info tracks cache statistics"""
        # Clear the cache before testing
        cache_admin_client.cache_clear()

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Check initial cache info
        info = cache_admin_client.cache_info()
        assert info.hits == 0
        assert info.misses == 0

        # First call - cache miss
        cache_admin_client()
        info = cache_admin_client.cache_info()
        assert info.hits == 0
        assert info.misses == 1

        # Second call - cache hit
        cache_admin_client()
        info = cache_admin_client.cache_info()
        assert info.hits == 1
        assert info.misses == 1

        # Third call - another cache hit
        cache_admin_client()
        info = cache_admin_client.cache_info()
        assert info.hits == 2
        assert info.misses == 1
