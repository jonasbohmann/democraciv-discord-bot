def distance(a, b):
    previous_distances = list(range(len(b)+1))
    current_distances = [0 for _ in range(len(b)+1)]

    for i in range(len(a)):
        current_distances[0] = i + 1

        for j in range(len(b)):
            current_distances[j+1] = min(
                previous_distances[j+1] + 1,
                current_distances[j] + 1,
                previous_distances[j] + (0 if a[i] == b[j] else 1)
            )

        previous_distances, current_distances = current_distances, previous_distances
    
    return previous_distances[-1]
