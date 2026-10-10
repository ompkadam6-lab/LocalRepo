Mira-Bhayandar Cultural Heritage Routing & Artisan Discovery Platform

Current baseline: original project + Heritage Detail + Multi-stop Dijkstra routing.

Run:
  pip install -r requirements.txt
  set AIVEN_DB_PASSWORD=YOUR_AIVEN_PASSWORD
  python app.py

Open:
  http://127.0.0.1:5000/

Important:
- No ER-diagram expansion is required for this version.
- Do NOT run any ER Phase-1 migration from older packages.
- The existing database tables remain the source of truth.
- The route planner supports start + multiple intermediate heritage sites + destination.
- Dijkstra calculates shortest paths; a nearest-neighbor heuristic orders selected stops.
- Google Maps receives the selected ordered stops as waypoints for live navigation.
- Google Maps waypoint limits should be respected (up to 3 on mobile browser, up to 9 otherwise).
- The project still uses Trie for autocomplete and Max Heap for artisan ranking.
