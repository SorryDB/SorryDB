from sorrydb.crawler.git_ops import remote_heads, remote_heads_hash
import logging
import unittest.mock as mock

def test_remote_heads():
    # Set up logging to see the debug messages
    logging.basicConfig(level=logging.DEBUG)

    # Test the functions
    url = "https://github.com/austinletson/sorryClientTestRepoMath"

    # Get and display all heads
    heads = remote_heads(url)
    print("\nFound branches:")
    for head in heads:
        print(f"Branch: {head['branch']:<40} SHA: {head['sha']}")

    # Get and display the combined hash
    hash_value = remote_heads_hash(url)
    print(f"\nCombined hash of all branch heads: {hash_value}") 

def test_remote_heads_hash_different():
    """Test that different sets of branch heads produce different hash values."""
    # Mock the remote_heads function to return controlled test data
    with mock.patch('sorrydb.crawler.git_ops.remote_heads') as mock_remote_heads:
        # First set of branch heads
        mock_remote_heads.return_value = [
            {'branch': 'main', 'sha': 'abc123'},
            {'branch': 'dev', 'sha': 'def456'}
        ]
        hash1 = remote_heads_hash("https://example.com/repo1")
        
        # Second set with update to one of the branches
        mock_remote_heads.return_value = [
            {'branch': 'main', 'sha': 'abc123'},
            {'branch': 'dev', 'sha': 'xyz789'}
        ]
        hash2 = remote_heads_hash("https://example.com/repo1")
        
        # Verify that different branch heads produce different hashes
        assert hash1 != hash2, "Modified branch should produce different hashes"

    with mock.patch('sorrydb.crawler.git_ops.remote_heads') as mock_remote_heads:
        # First set of branch heads
        mock_remote_heads.return_value = [
            {'branch': 'main', 'sha': 'abc123'},
            {'branch': 'dev', 'sha': 'def456'}
        ]
        hash1 = remote_heads_hash("https://example.com/repo1")
        
        # Second set with new branch
        mock_remote_heads.return_value = [
            {'branch': 'main', 'sha': 'abc123'},
            {'branch': 'dev', 'sha': 'def456'},
            {'branch': 'feature-branch', 'sha': 'ghi789'}
        ]
        hash2 = remote_heads_hash("https://example.com/repo1")
        
        # Verify that different branch heads produce different hashes
        assert hash1 != hash2, "Additional branch should produce different hashes"