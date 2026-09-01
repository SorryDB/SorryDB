from sorrydb.database.github_index import size_shards


def counter(sizes):
    """Stand-in for GitHub's `total_count` over an inclusive size range."""
    return lambda lo, hi: sum(1 for size in sizes if lo <= size <= hi)


def check_covers(shards, sizes, cap):
    # every size lands in exactly one shard
    for size in sizes:
        assert sum(1 for lo, hi in shards if lo <= size <= hi) == 1
    for lo, hi in shards:
        assert counter(sizes)(lo, hi) <= cap or lo == hi


def test_shards_split_until_under_cap():
    # 2500 manifests clustered where real ones are, well over the cap
    sizes = [200 + (i * 7) % 4000 for i in range(2500)]
    shards = size_shards(counter(sizes), cap=1000)
    check_covers(shards, sizes, 1000)


def test_no_split_needed():
    sizes = [500, 1500, 90000]
    assert size_shards(counter(sizes), cap=1000) == [(0, 1024 * 1024)]


def test_unsplittable_shard_still_covers():
    # 2000 manifests of identical size cannot be split below the cap
    sizes = [500] * 2000
    shards = size_shards(counter(sizes), cap=1000)
    check_covers(shards, sizes, 1000)
    assert any(lo == hi == 500 for lo, hi in shards)
