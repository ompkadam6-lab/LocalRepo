import mysql.connector
import os


# ---------------------------------
# Max Heap
# ---------------------------------

class MaxHeap:

    def __init__(self):
        self.heap = []

    def insert(self, artisan):
        self.heap.append(artisan)
        self._heapify_up(len(self.heap) - 1)

    def _heapify_up(self, index):

        while index > 0:

            parent = (index - 1) // 2

            if self.heap[parent][1] >= self.heap[index][1]:
                break

            self.heap[parent], self.heap[index] = \
                self.heap[index], self.heap[parent]

            index = parent

    def extract_max(self):

        if not self.heap:
            return None

        if len(self.heap) == 1:
            return self.heap.pop()

        maximum = self.heap[0]

        self.heap[0] = self.heap.pop()

        self._heapify_down(0)

        return maximum

    def _heapify_down(self, index):

        size = len(self.heap)

        while True:

            largest = index

            left = 2 * index + 1
            right = 2 * index + 2

            if (
                left < size
                and self.heap[left][1] > self.heap[largest][1]
            ):
                largest = left

            if (
                right < size
                and self.heap[right][1] > self.heap[largest][1]
            ):
                largest = right

            if largest == index:
                break

            self.heap[index], self.heap[largest] = \
                self.heap[largest], self.heap[index]

            index = largest


# ---------------------------------
# Connect to Aiven MySQL
# ---------------------------------

connection = mysql.connector.connect(
    host="mysql-2ff33ec-om2000kadam-dc6d.l.aivencloud.com",
    port=12747,
    user="avnadmin",
    "password": os.environ["AIVEN_DB_PASSWORD"],
    database="defaultdb",
    ssl_disabled=False
)

cursor = connection.cursor()


# ---------------------------------
# Get Artisans
# ---------------------------------

cursor.execute("""
    SELECT ArtisanID, ArtisanName, Location, Rating
    FROM artisans
""")

artisans = cursor.fetchall()


# ---------------------------------
# Create Max Heap
# ---------------------------------

heap = MaxHeap()


for artisan in artisans:

    artisan_id = artisan[0]
    name = artisan[1]
    location = artisan[2]
    rating = float(artisan[3])

    heap.insert(
        (name, rating, location, artisan_id)
    )


# ---------------------------------
# Display Ranked Artisans
# ---------------------------------

print("\nTop Recommended Artisans:")
print("--------------------------")

rank = 1

while heap.heap:

    artisan = heap.extract_max()

    name = artisan[0]
    rating = artisan[1]
    location = artisan[2]

    print(
        f"{rank}. {name} | "
        f"Rating: {rating:.2f} | "
        f"Location: {location}"
    )

    rank += 1


# ---------------------------------
# Close Connection
# ---------------------------------

cursor.close()
connection.close()