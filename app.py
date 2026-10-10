from flask import Flask, render_template, request, abort, jsonify
import os
import json
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import mysql.connector
from trie import Trie

app = Flask(__name__)

# =========================================================
# DATABASE CONFIGURATION
# Replace YOUR_AIVEN_PASSWORD with your Aiven password.
# Better: set AIVEN_DB_PASSWORD as an environment variable.
# =========================================================
DB_CONFIG = {
    "host": "mysql-2ff33ec-om2000kadam-dc6d.l.aivencloud.com",
    "port": 12747,
    "user": "avnadmin",
    "password": os.environ["AIVEN_DB_PASSWORD"],
    "database": "defaultdb",
    "ssl_disabled": False
}


class MaxHeap:
    def __init__(self):
        self.heap = []

    def insert(self, artisan):
        self.heap.append(artisan)
        self._heapify_up(len(self.heap) - 1)

    def _heapify_up(self, i):
        while i > 0:
            p = (i - 1) // 2
            if float(self.heap[p]["Rating"] or 0) >= float(self.heap[i]["Rating"] or 0):
                break
            self.heap[p], self.heap[i] = self.heap[i], self.heap[p]
            i = p

    def extract_max(self):
        if not self.heap:
            return None
        maximum = self.heap[0]
        last = self.heap.pop()
        if self.heap:
            self.heap[0] = last
            self._heapify_down(0)
        return maximum

    def _heapify_down(self, i):
        n = len(self.heap)
        while True:
            largest = i
            l, r = 2 * i + 1, 2 * i + 2
            if l < n and float(self.heap[l]["Rating"] or 0) > float(self.heap[largest]["Rating"] or 0):
                largest = l
            if r < n and float(self.heap[r]["Rating"] or 0) > float(self.heap[largest]["Rating"] or 0):
                largest = r
            if largest == i:
                break
            self.heap[i], self.heap[largest] = self.heap[largest], self.heap[i]
            i = largest


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def dijkstra(graph, start):
    distances = {node: float("inf") for node in graph}
    previous = {node: None for node in graph}
    if start not in distances:
        distances[start] = 0
        previous[start] = None

    distances[start] = 0
    unvisited = set(graph.keys())

    while unvisited:
        current = min(unvisited, key=lambda x: distances[x])
        if distances[current] == float("inf"):
            break
        unvisited.remove(current)

        for neighbor, weight in graph[current]:
            new_distance = distances[current] + weight
            if new_distance < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_distance
                previous[neighbor] = current

    return distances, previous


def reconstruct_path(previous, start, destination):
    path = []
    current = destination

    while current is not None:
        path.append(current)
        if current == start:
            path.reverse()
            return path
        current = previous.get(current)

    return []


def fetchone_dict(cursor, query, params=()):
    cursor.execute(query, params)
    return cursor.fetchone()


def fetchall_dict(cursor, query, params=()):
    cursor.execute(query, params)
    return cursor.fetchall()


# =========================================================
# GOOGLE PLACES (NEW) - OPTIONAL SERVER-SIDE INTEGRATION
# =========================================================
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
GOOGLE_PLACES_BASE = "https://places.googleapis.com/v1"


def _google_request(url, method="GET", body=None, field_mask=None):
    """Make a small server-side Google Places API request.

    The API key is never sent to the browser. Reviews are fetched only when
    the user explicitly clicks the Load Google Reviews button.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
    }
    if field_mask:
        headers["X-Goog-FieldMask"] = field_mask

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            details = exc.read().decode("utf-8", errors="replace")
            payload = json.loads(details) if details else {}
        except Exception:
            payload = {"error": {"message": str(exc)}}
        message = payload.get("error", {}).get("message") or f"Google Places API error ({exc.code})."
        raise RuntimeError(message) from exc
    except URLError as exc:
        raise RuntimeError("Unable to reach Google Places right now. Please try again.") from exc


def _heritage_google_place_column(cur):
    """Return whether GooglePlaceID exists without requiring a migration."""
    cur.execute("""
        SELECT COUNT(*) AS column_count
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'heritage_sites'
          AND COLUMN_NAME = 'GooglePlaceID'
    """)
    row = cur.fetchone()
    return bool(row and row.get("column_count", 0))


def _get_site_for_google(cur, site_id):
    has_column = _heritage_google_place_column(cur)
    fields = "SiteID, SiteName, Location, Latitude, Longitude"
    if has_column:
        fields += ", GooglePlaceID"

    cur.execute(f"SELECT {fields} FROM heritage_sites WHERE SiteID = %s", (site_id,))
    site = cur.fetchone()
    if site and "GooglePlaceID" not in site:
        site["GooglePlaceID"] = None
    return site, has_column


def _discover_google_place(site):
    """Find a likely Google Place ID from the project's site name/location."""
    query_parts = [site["SiteName"]]
    if site.get("Location"):
        query_parts.append(site["Location"])
    query_parts.append("Mira-Bhayandar, Maharashtra, India")

    payload = _google_request(
        f"{GOOGLE_PLACES_BASE}/places:searchText",
        method="POST",
        body={"textQuery": ", ".join(query_parts), "pageSize": 1},
        field_mask="places.id,places.displayName,places.formattedAddress,places.googleMapsUri"
    )

    places = payload.get("places") or []
    return places[0] if places else None


def _get_google_place_details(place_id):
    return _google_request(
        f"{GOOGLE_PLACES_BASE}/places/{quote(place_id, safe='')}",
        method="GET",
        field_mask=(
            "id,displayName,rating,userRatingCount,reviews,"
            "googleMapsUri,googleMapsLinks.reviewsUri"
        )
    )


def _normalize_google_reviews(place):
    """Convert the Places API response into a template-friendly structure."""
    normalized = []
    for review in (place.get("reviews") or [])[:5]:
        author = review.get("authorAttribution") or {}
        localized = review.get("text") or {}
        normalized.append({
            "rating": review.get("rating"),
            "text": localized.get("text") or "",
            "author": author.get("displayName") or "Google user",
            "author_uri": author.get("uri"),
            "author_photo": author.get("photoUri"),
            "relative_time": review.get("relativePublishTimeDescription") or "",
            "publish_time": review.get("publishTime") or "",
            "google_maps_uri": review.get("googleMapsUri")
        })
    return normalized


@app.route("/api/google-reviews/<int:site_id>")
def google_reviews(site_id):
    """Return Google rating/reviews for one heritage site.

    Without a configured API key, this endpoint intentionally does not call
    Google and returns a Maps link instead. With a key, it uses Places API
    (New) and caches the discovered Place ID when the optional column exists.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    try:
        site, has_place_column = _get_site_for_google(cur, site_id)
        if not site:
            return jsonify({"ok": False, "message": "Heritage site not found."}), 404

        maps_query = site.get("Latitude") and site.get("Longitude")
        fallback_maps_url = (
            "https://www.google.com/maps/search/?api=1&query="
            + quote(f"{site['SiteName']}, {site['Location']}, Mira-Bhayandar")
        )
        if maps_query:
            fallback_maps_url = (
                "https://www.google.com/maps/search/?api=1&query="
                + quote(f"{site['Latitude']},{site['Longitude']}")
            )

        if not GOOGLE_PLACES_API_KEY:
            return jsonify({
                "ok": True,
                "configured": False,
                "site_name": site["SiteName"],
                "message": "Google Places API is not configured. Use Google Maps to read the live reviews.",
                "google_maps_url": fallback_maps_url
            })

        place_id = site.get("GooglePlaceID")
        discovered = None

        if not place_id:
            discovered = _discover_google_place(site)
            if not discovered:
                return jsonify({
                    "ok": True,
                    "configured": True,
                    "site_name": site["SiteName"],
                    "found": False,
                    "message": "Google could not confidently match this heritage site.",
                    "google_maps_url": fallback_maps_url
                })
            place_id = discovered.get("id")

            if place_id and has_place_column:
                cur.execute(
                    "UPDATE heritage_sites SET GooglePlaceID = %s WHERE SiteID = %s",
                    (place_id, site_id)
                )
                conn.commit()

        place = _get_google_place_details(place_id)
        reviews = _normalize_google_reviews(place)
        maps_url = place.get("googleMapsUri") or fallback_maps_url
        links = place.get("googleMapsLinks") or {}
        reviews_url = links.get("reviewsUri") or maps_url

        return jsonify({
            "ok": True,
            "configured": True,
            "found": True,
            "site_name": site["SiteName"],
            "place_id": place_id,
            "display_name": (place.get("displayName") or {}).get("text") or site["SiteName"],
            "rating": place.get("rating"),
            "user_rating_count": place.get("userRatingCount"),
            "reviews": reviews,
            "google_maps_url": maps_url,
            "reviews_url": reviews_url,
            "attribution": "Google Maps"
        })
    except RuntimeError as exc:
        return jsonify({
            "ok": False,
            "configured": bool(GOOGLE_PLACES_API_KEY),
            "message": str(exc),
            "google_maps_url": fallback_maps_url if 'fallback_maps_url' in locals() else None
        }), 502
    finally:
        cur.close()
        conn.close()


@app.route("/")
def home():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    sites = fetchall_dict(cur, """
        SELECT SiteID, SiteName, Description, Location, Latitude,
               Longitude, Category, EntryFee
        FROM heritage_sites
        ORDER BY SiteID
    """)

    artisans = fetchall_dict(cur, """
        SELECT a.ArtisanID, a.ArtisanName, a.ContactNo, a.Location,
               a.ExperienceYears, a.Rating, a.CraftID,
               c.CraftName, c.Category AS CraftCategory
        FROM artisans a
        LEFT JOIN crafts c ON a.CraftID = c.CraftID
        ORDER BY a.Rating DESC
    """)

    articles = fetchall_dict(cur, """
        SELECT ArticleID, Title, Summary, CoverImageURL, Category,
               AuthorName, PublishedDate
        FROM articles
        ORDER BY PublishedDate DESC
        LIMIT 4
    """)

    experiences = fetchall_dict(cur, """
        SELECT e.*, a.ArtisanName, h.SiteName
        FROM experiences e
        LEFT JOIN artisans a ON e.ArtisanID = a.ArtisanID
        LEFT JOIN heritage_sites h ON e.SiteID = h.SiteID
        ORDER BY e.ExperienceID DESC
        LIMIT 6
    """)

    videos = fetchall_dict(cur, """
        SELECT VideoID, Title, Description, VideoURL, ThumbnailURL, Category
        FROM videos
        ORDER BY PublishedDate DESC
        LIMIT 4
    """)

    # Max-Heap: top-rated artisans
    heap = MaxHeap()
    for artisan in artisans:
        heap.insert(artisan)

    top_artisans = []
    for _ in range(min(3, len(artisans))):
        item = heap.extract_max()
        if item:
            top_artisans.append(item)

    # Trie: autocomplete/search
    trie = Trie()
    for site in sites:
        trie.insert(site["SiteName"], site["SiteName"])
        for word in site["SiteName"].split():
            trie.insert(word, site["SiteName"])

    cur.close()
    conn.close()

    q = request.args.get("q", "").strip()
    search_results = trie.starts_with(q) if q else []

    return render_template(
        "index.html",
        sites=sites,
        artisans=artisans,
        top_artisans=top_artisans,
        articles=articles,
        experiences=experiences,
        videos=videos,
        search_query=q,
        search_results=search_results
    )


@app.route("/heritage/<int:site_id>")
def heritage_detail(site_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    site = fetchone_dict(cur, """
        SELECT * FROM heritage_sites WHERE SiteID = %s
    """, (site_id,))

    if not site:
        cur.close()
        conn.close()
        abort(404)

    gallery = fetchall_dict(cur, """
        SELECT * FROM site_gallery
        WHERE SiteID = %s
        ORDER BY GalleryID
    """, (site_id,))

    related_articles = fetchall_dict(cur, """
        SELECT ArticleID, Title, Summary, CoverImageURL, Category
        FROM articles
        WHERE SiteID = %s
        ORDER BY PublishedDate DESC
    """, (site_id,))

    related_videos = fetchall_dict(cur, """
        SELECT VideoID, Title, Description, VideoURL, ThumbnailURL
        FROM videos
        WHERE SiteID = %s OR SiteID IS NULL
        ORDER BY CASE WHEN SiteID = %s THEN 0 ELSE 1 END, PublishedDate DESC
        LIMIT 6
    """, (site_id, site_id))

    nearby_artisans = fetchall_dict(cur, """
        SELECT a.ArtisanID, a.ArtisanName, a.Location, a.ExperienceYears,
               a.Rating, c.CraftName, c.Category AS CraftCategory
        FROM artisans a
        LEFT JOIN crafts c ON a.CraftID = c.CraftID
        WHERE a.Location = %s
           OR a.Location LIKE CONCAT('%%', %s, '%%')
           OR %s LIKE CONCAT('%%', a.Location, '%%')
        ORDER BY a.Rating DESC
        LIMIT 6
    """, (site["Location"], site["Location"], site["Location"]))

    related_experiences = fetchall_dict(cur, """
        SELECT e.*, a.ArtisanName
        FROM experiences e
        LEFT JOIN artisans a ON e.ArtisanID = a.ArtisanID
        WHERE e.SiteID = %s OR e.SiteID IS NULL
        ORDER BY CASE WHEN e.SiteID = %s THEN 0 ELSE 1 END, e.ExperienceID DESC
        LIMIT 6
    """, (site_id, site_id))

    reviews = fetchall_dict(cur, """
        SELECT r.Rating, r.Comment, r.ReviewDate, u.Name
        FROM reviews r
        JOIN users u ON r.UserID = u.UserID
        WHERE r.SiteID = %s
        ORDER BY r.ReviewDate DESC
    """, (site_id,))

    cur.close()
    conn.close()

    return render_template(
        "heritage_detail.html",
        site=site,
        gallery=gallery,
        articles=related_articles,
        videos=related_videos,
        nearby_artisans=nearby_artisans,
        experiences=related_experiences,
        reviews=reviews
    )


@app.route("/artisans")
def artisan_list():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    artisans = fetchall_dict(cur, """
        SELECT a.*, c.CraftName, c.Category AS CraftCategory
        FROM artisans a
        LEFT JOIN crafts c ON a.CraftID = c.CraftID
        ORDER BY a.Rating DESC
    """)

    cur.close()
    conn.close()
    return render_template("artisans.html", artisans=artisans)


@app.route("/artisan/<int:artisan_id>")
def artisan_detail(artisan_id):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    artisan = fetchone_dict(cur, """
        SELECT a.*, c.CraftName, c.Category AS CraftCategory,
               c.Description AS CraftDescription
        FROM artisans a
        LEFT JOIN crafts c ON a.CraftID = c.CraftID
        WHERE a.ArtisanID = %s
    """, (artisan_id,))

    if not artisan:
        cur.close()
        conn.close()
        abort(404)

    gallery = fetchall_dict(cur, """
        SELECT * FROM artisan_gallery
        WHERE ArtisanID = %s
        ORDER BY GalleryID
    """, (artisan_id,))

    reviews = fetchall_dict(cur, """
        SELECT r.Rating, r.Comment, r.ReviewDate, u.Name
        FROM reviews r
        JOIN users u ON r.UserID = u.UserID
        WHERE r.ArtisanID = %s
        ORDER BY r.ReviewDate DESC
    """, (artisan_id,))

    experiences = fetchall_dict(cur, """
        SELECT * FROM experiences
        WHERE ArtisanID = %s
        ORDER BY ExperienceID DESC
    """, (artisan_id,))

    cur.close()
    conn.close()

    return render_template(
        "artisan_detail.html",
        artisan=artisan,
        gallery=gallery,
        reviews=reviews,
        experiences=experiences
    )


@app.route("/articles")
def articles_page():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    articles = fetchall_dict(cur, """
        SELECT a.*, h.SiteName, c.CraftName
        FROM articles a
        LEFT JOIN heritage_sites h ON a.SiteID = h.SiteID
        LEFT JOIN crafts c ON a.CraftID = c.CraftID
        ORDER BY a.PublishedDate DESC
    """)

    cur.close()
    conn.close()
    return render_template("articles.html", articles=articles)


@app.route("/videos")
def videos_page():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    videos = fetchall_dict(cur, """
        SELECT v.*, h.SiteName, c.CraftName, a.ArtisanName
        FROM videos v
        LEFT JOIN heritage_sites h ON v.SiteID = h.SiteID
        LEFT JOIN crafts c ON v.CraftID = c.CraftID
        LEFT JOIN artisans a ON v.ArtisanID = a.ArtisanID
        ORDER BY v.PublishedDate DESC
    """)

    cur.close()
    conn.close()
    return render_template("videos.html", videos=videos)


@app.route("/experiences")
def experiences_page():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    experiences = fetchall_dict(cur, """
        SELECT e.*, h.SiteName, a.ArtisanName
        FROM experiences e
        LEFT JOIN heritage_sites h ON e.SiteID = h.SiteID
        LEFT JOIN artisans a ON e.ArtisanID = a.ArtisanID
        ORDER BY e.ExperienceID DESC
    """)

    cur.close()
    conn.close()
    return render_template("experiences.html", experiences=experiences)


@app.route("/routes")
def routes_page():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)

    sites = fetchall_dict(cur, """
        SELECT SiteID, SiteName, Location
        FROM heritage_sites
        ORDER BY SiteName
    """)

    connections = fetchall_dict(cur, """
        SELECT FromSiteID, ToSiteID, Distance
        FROM site_connections
    """)

    graph = {}
    for row in connections:
        graph.setdefault(row["FromSiteID"], []).append(
            (row["ToSiteID"], float(row["Distance"]))
        )
        graph.setdefault(row["ToSiteID"], [])

    site_map = {s["SiteID"]: s for s in sites}

    start = request.args.get("start", type=int)
    destination = request.args.get("destination", type=int)
    raw_stops = request.args.getlist("stops")
    stops = []
    for value in raw_stops:
        try:
            site_id = int(value)
            if site_id in site_map and site_id not in stops:
                stops.append(site_id)
        except (TypeError, ValueError):
            continue

    # Do not allow the start or destination to also be a waypoint.
    if start in stops:
        stops.remove(start)
    if destination in stops:
        stops.remove(destination)

    route_names = []
    ordered_stop_ids = []
    ordered_stop_names = []
    route_distance = None
    google_maps_url = None
    start_name = site_map.get(start, {}).get("SiteName") if start else None
    destination_name = site_map.get(destination, {}).get("SiteName") if destination else None
    error_message = None

    def shortest_segment(source, target):
        """Return (distance, path) for one source→target Dijkstra segment."""
        if source not in graph:
            graph[source] = []
        distances, previous = dijkstra(graph, source)
        distance = distances.get(target, float("inf"))
        if distance == float("inf"):
            return None, []
        return distance, reconstruct_path(previous, source, target)

    if start and destination:
        if start == destination:
            error_message = "Start and destination must be different locations."
        elif start not in site_map or destination not in site_map:
            error_message = "One of the selected locations does not exist."
        elif len(stops) > 9:
            error_message = "Please choose at most 9 intermediate stops so the route can be handed off to Google Maps."
        else:
            # Multi-stop route ordering:
            # Dijkstra gives the shortest graph distance between each pair.
            # A nearest-neighbor heuristic then chooses the next unvisited stop.
            current = start
            remaining = stops[:]
            ordered_segments = []
            total_distance = 0.0
            final_path = []
            segment_cache = {}

            while remaining:
                best_stop = None
                best_distance = float("inf")
                best_path = []

                for candidate in remaining:
                    cache_key = (current, candidate)
                    if cache_key not in segment_cache:
                        segment_cache[cache_key] = shortest_segment(current, candidate)
                    distance, path = segment_cache[cache_key]
                    if distance is not None and distance < best_distance:
                        best_stop = candidate
                        best_distance = distance
                        best_path = path

                if best_stop is None:
                    error_message = "No connected route was found for all selected stops. Try removing one of the stops."
                    break

                ordered_segments.append((current, best_stop, best_distance, best_path))
                total_distance += best_distance
                if not final_path:
                    final_path.extend(best_path)
                else:
                    final_path.extend(best_path[1:])
                current = best_stop
                remaining.remove(best_stop)

            if not error_message:
                cache_key = (current, destination)
                if cache_key not in segment_cache:
                    segment_cache[cache_key] = shortest_segment(current, destination)
                final_distance, final_segment_path = segment_cache[cache_key]

                if final_distance is None:
                    error_message = "The destination is not connected to the selected cultural stops. Try a different destination."
                else:
                    total_distance += final_distance
                    if not final_path:
                        final_path.extend(final_segment_path)
                    else:
                        final_path.extend(final_segment_path[1:])

                    ordered_stop_ids = [segment[1] for segment in ordered_segments]
                    ordered_stop_names = [site_map[sid]["SiteName"] for sid in ordered_stop_ids]
                    route_names = [site_map[sid]["SiteName"] for sid in final_path if sid in site_map]
                    route_distance = total_distance

                    # Google Maps receives the selected stop order rather than every
                    # internal Dijkstra graph node. Google Maps then supplies live
                    # road directions and traffic.
                    waypoint_ids = ordered_stop_ids[:9]
                    origin = quote(start_name or "")
                    destination_param = quote(destination_name or "")
                    google_maps_url = (
                        "https://www.google.com/maps/dir/?api=1"
                        f"&origin={origin}&destination={destination_param}&travelmode=driving"
                    )
                    if waypoint_ids:
                        waypoint_text = "|".join(
                            quote(site_map[sid]["SiteName"]) for sid in waypoint_ids
                        )
                        google_maps_url += f"&waypoints={waypoint_text}"

    cur.close()
    conn.close()

    return render_template(
        "routes.html",
        sites=sites,
        route_names=route_names,
        route_distance=route_distance,
        start=start,
        destination=destination,
        selected_stops=stops,
        ordered_stop_ids=ordered_stop_ids,
        ordered_stop_names=ordered_stop_names,
        start_name=start_name,
        destination_name=destination_name,
        google_maps_url=google_maps_url,
        error_message=error_message
    )


if __name__ == "__main__":
    app.run(debug=True)
