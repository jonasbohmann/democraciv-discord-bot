def distance(a, b):
    return distance2(a, b, len(a), len(b))

def distance2(a, b, i, j):
    if min(i, j) == 0:
        return max(i, j)
    else:
        return min(
            distance2(a, b, i-1, j) + 1,
            distance2(a, b, i, j-1) + 1,
            distance2(a, b, i-1, j-1) + (1 if a[i-1] != b[j-1] else 0)
        )
