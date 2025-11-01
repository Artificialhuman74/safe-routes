#!/bin/bash

echo "Testing Safe Route API..."
echo "========================="
echo ""

# Test route generation
curl -s -X POST http://localhost:5000/api/optimize-route \
  -H "Content-Type: application/json" \
  -d '{
    "start_lat": 12.9918,
    "start_lon": 77.5837,
    "end_lat": 12.9631,
    "end_lon": 77.6110,
    "safety_weight": 0.6,
    "distance_weight": 0.4,
    "prefer_main_roads": false,
    "prefer_well_lit": true,
    "prefer_populated": true
  }' | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'✅ Success: {data.get(\"success\")}')
print(f'📊 Routes Found: {len(data.get(\"routes\", []))}')
print(f'📊 Total Analyzed: {data.get(\"total_analyzed\")}')
print(f'📊 Pareto Optimal: {data.get(\"pareto_optimal\")}')
print('')
print('Route Details:')
for i, r in enumerate(data.get('routes', [])):
    print(f'  Route {i+1}: Safety={r.get(\"safety_score\", 0):.1f}/100, Crime={r.get(\"crime_density\", 0):.2f}, Distance={r.get(\"distance_km\", 0):.2f}km')
"

echo ""
echo "Check the Flask log output to see waypoint generation details"

