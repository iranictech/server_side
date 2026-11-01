"""Deterministic initial ranking. No semantic model yet."""


def rank_internal(candidates):
    def sort_key(item):
        load = item["active_reviews"]
        return (
            -len(item["matched_keywords"]),
            load is None,
            load if load is not None else 0,
            item["account_id"],
        )

    return sorted(candidates, key=sort_key)
