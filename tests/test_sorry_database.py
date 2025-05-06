from sorrydb.database.sorry_database import JsonDatabase


def test_ignore_repos(update_db_single_test_repo_path):
    database = JsonDatabase()

    database.load_database(update_db_single_test_repo_path)

    # call get_repos ignoring the only repo in the mock database
    repos_with_ignore = database.get_repos(
        ignore_list=["https://github.com/austinletson/sorryClientTestRepo"]
    )

    assert len(list(repos_with_ignore)) == 0
