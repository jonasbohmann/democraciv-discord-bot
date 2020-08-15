def distance(a, b):
    distances = [[0 for _ in range(len(b)+1)] for _ in range(len(a)+1)]

    for i in range(len(a)):
        distances[i+1][0] = i+1
    
    for j in range(len(b)):
        distances[0][j+1] = j+1
    
    for i in range(len(a)):
        for j in range(len(b)):
            distances[i+1][j+1] = min(
                distances[i][j+1] + 1,
                distances[i+1][j] + 1,
                distances[i][j] + (0 if a[i] == b[j] else 1)
            )
    
    return distances[-1][-1]

# Temprorary, for performance testing
if __name__ == "__main__":
    import timeit
    print(timeit.timeit(stmt="distance('foo', 'barrr')", number=1000, globals=globals()))
