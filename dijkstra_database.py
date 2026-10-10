import mysql.connector
import heapq
import os


# Connect to Aiven MySQL
connection = mysql.connector.connect(
    host="mysql-2ff33ec-om2000kadam-dc6d.l.aivencloud.com",
    port=12747,
    user="avnadmin",
    "password": os.environ["AIVEN_DB_PASSWORD"],
    database="defaultdb",
    ssl_disabled=False
)

cursor = connection.cursor()

# Get site names
cursor.execute("""
    SELECT SiteID, SiteName
    FROM heritage_sites
""")

site_rows = cursor.fetchall()

site_names = {}

for site_id, site_name in site_rows:
    site_names[site_id] = site_name


# Get graph connections
cursor.execute("""
    SELECT FromSiteID, ToSiteID, Distance
    FROM site_connections
""")

rows = cursor.fetchall()

graph = {}

for from_site, to_site, distance in rows:

    if from_site not in graph:
        graph[from_site] = []

    graph[from_site].append(
        (to_site, float(distance))
    )


# Dijkstra Algorithm
def dijkstra(graph, start):

    distances = {
        node: float('inf')
        for node in graph
    }

    previous = {
        node: None
        for node in graph
    }

    distances[start] = 0

    priority_queue = [(0, start)]

    while priority_queue:

        current_distance, current_node = heapq.heappop(
            priority_queue
        )

        if current_distance > distances[current_node]:
            continue

        for neighbor, weight in graph[current_node]:

            distance = current_distance + weight

            if distance < distances[neighbor]:

                distances[neighbor] = distance
                previous[neighbor] = current_node

                heapq.heappush(
                    priority_queue,
                    (distance, neighbor)
                )

    return distances, previous


# Start from Uttan Heritage Village
start_site = 1

distances, previous = dijkstra(
    graph,
    start_site
)


print("\nShortest routes from:",
      site_names[start_site])

print("-" * 50)

for site_id, distance in distances.items():

    print(
        site_names[site_id],
        "->",
        round(distance, 2),
        "km"
    )


cursor.close()
connection.close()