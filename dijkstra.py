import heapq

# Graph:
# 1 = Uttan Heritage Village
# 2 = Ghodbunder Fort
# 3 = Bhayandar Heritage Area

graph = {
    1: [(2, 8.50), (3, 5.20)],
    2: [(1, 8.50), (3, 6.00)],
    3: [(1, 5.20), (2, 6.00)]
}


def dijkstra(graph, start):
    distances = {node: float('inf') for node in graph}
    previous = {node: None for node in graph}

    distances[start] = 0

    priority_queue = [(0, start)]

    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)

        if current_distance > distances[current_node]:
            continue

        for neighbor, weight in graph[current_node]:
            distance = current_distance + weight

            if distance < distances[neighbor]:
                distances[neighbor] = distance
                previous[neighbor] = current_node
                heapq.heappush(priority_queue, (distance, neighbor))

    return distances, previous


def get_path(previous, start, destination):
    path = []
    current = destination

    while current is not None:
        path.append(current)
        current = previous[current]

    path.reverse()

    if path[0] != start:
        return []

    return path


# Find shortest routes from Uttan
distances, previous = dijkstra(graph, 1)

print("Shortest distances from Uttan Heritage Village:")
print(distances)

print("\nShortest path from Uttan to Bhayandar:")

path = get_path(previous, 1, 3)

print(" -> ".join(map(str, path)))
print("Distance:", distances[3], "km")