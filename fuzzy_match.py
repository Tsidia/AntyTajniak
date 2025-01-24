# fuzzy_match.py

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Compute the Levenshtein distance between two strings (case-insensitive).
    """
    s1 = s1.upper()
    s2 = s2.upper()
    m, n = len(s1), len(s2)

    if m == 0:
        return n
    if n == 0:
        return m

    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,         # deletion
                dp[i][j - 1] + 1,         # insertion
                dp[i - 1][j - 1] + cost   # substitution
            )
    return dp[m][n]


def fuzzy_match(recognized_text: str, db_entries, mismatch_tolerance: int):
    """
    Return a matching plate from `db_entries` if recognized_text is 
    within `mismatch_tolerance` of any DB plate. Otherwise return None.
    """
    recognized_text = recognized_text.strip().upper()
    if not recognized_text:
        return None

    best_match = None
    best_dist = float('inf')
    for db_plate in db_entries:
        dist = levenshtein_distance(recognized_text, db_plate)
        if dist < best_dist:
            best_dist = dist
            best_match = db_plate

    if best_dist <= mismatch_tolerance:
        return best_match
    return None
