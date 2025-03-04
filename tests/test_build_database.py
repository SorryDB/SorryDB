from sorrydb.database.build_database import prepare_and_process_lean_repo


def test_prepare_and_process_lean_repo_with_mutiple_lean_versions():
    """
    Verify that the database builder can handle repositories
    that use different versions of Lean.
    
    sorryClientTestRepoMath uses v4.17.0-rc1 and sorryClientTestRepo uses v4.16.0
    """
    mathRepoResults = prepare_and_process_lean_repo(
        repo_url='https://github.com/austinletson/sorryClientTestRepoMath',
    )

    assert len(mathRepoResults["sorries"]) > 0
    repoResults = prepare_and_process_lean_repo(
        repo_url='https://github.com/austinletson/sorryClientTestRepo',
    )

    assert len(repoResults["sorries"]) > 0
