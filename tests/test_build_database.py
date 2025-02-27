from sorrydb.database.build_database import build_database


def test_build_database_with_mutiple_lean_versions():
    """
    Verify that the database builder can handle repositories
    that use different versions of Lean.
    
    sorryClientTestRepoMath uses v4.17.0-rc1 and sorryClientTestRepo uses v4.16.0
    """
    mathRepoResults = build_database(
        repo_url='https://github.com/austinletson/sorryClientTestRepoMath',
    )

    assert len(mathRepoResults["sorries"]) > 0
    repoResults = build_database(
        repo_url='https://github.com/austinletson/sorryClientTestRepo',
    )

    assert len(repoResults["sorries"]) > 0
