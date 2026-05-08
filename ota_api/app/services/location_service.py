from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from app.models.otadb.Airport import Airport
from app.models.otadb.City import City
from app.models.otadb.Country import Country
from app.utils.redis_utils import redis_helper
import hashlib
from difflib import SequenceMatcher

class LocationService:
    SUPER_HUBS = {
        'LHR', 'JFK', 'DXB', 'SIN', 'HND', 'CDG', 'AMS', 'IST', 'FRA', 
        'CAN', 'ATL', 'ORD', 'DFW', 'DEN', 'LAX', 'MAD', 'BKK', 'DEL', 
        'ICN', 'PEK', 'SYD', 'BOM', 'MUC', 'ZRH', 'HKG', 'DOH'
    }

    def __init__(self, db: Session):
        self.db = db
        self.cache_ttl = 3600

    def _get_fuzzy_ratio(self, a, b):
        if not a or not b:
            return 0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def search_locations(self, query: str, limit: int = 15):
        if not query:
            return []

        # Sanitize and limit input length for security
        query = query.strip().lower()[:50]
        
        cache_key = f"loc_search_opt:{hashlib.md5(query.encode()).hexdigest()}"
        cached_results = redis_helper.get_data(cache_key)
        if cached_results:
            return cached_results

        search_term = f"%{query}%"
        fetch_limit = limit * 3

        # Optimized Search: Use joinedload to prevent N+1 queries
        city_results = (
            self.db.query(City)
            .options(joinedload(City.country))
            .filter(City.status == 'Active')
            .filter(
                or_(
                    City.name.ilike(search_term),
                    City.iata_code.ilike(query)
                )
            )
            .limit(fetch_limit)
            .all()
        )

        airport_results = (
            self.db.query(Airport)
            .options(joinedload(Airport.city), joinedload(Airport.country))
            .filter(Airport.status == 'Active')
            .filter(
                or_(
                    Airport.iata_code.ilike(query),
                    Airport.name.ilike(search_term)
                )
            )
            .limit(fetch_limit)
            .all()
        )

        formatted_results = []
        seen_codes = set()

        for city in city_results:
            code = city.iata_code or ""
            if code and code not in seen_codes:
                city_name = city.name or "Unknown"
                ratio = max(self._get_fuzzy_ratio(query, code), self._get_fuzzy_ratio(query, city_name))
                formatted_results.append({
                    "code": code,
                    "name": "All Airports",
                    "city": city_name,
                    "country": city.country.name if city.country else "Unknown",
                    "type": "city",
                    "score": ratio,
                    "is_hub": 1 if code in self.SUPER_HUBS else 0,
                    "is_intl": 1
                })
                seen_codes.add(code)

        for airport in airport_results:
            code = airport.iata_code or ""
            if code and code not in seen_codes:
                airport_name = airport.name or "Unknown"
                city_name = airport.city.name if airport.city else "Unknown"
                ratio = max(self._get_fuzzy_ratio(query, code), self._get_fuzzy_ratio(query, airport_name), self._get_fuzzy_ratio(query, city_name))
                formatted_results.append({
                    "code": code,
                    "name": airport_name,
                    "city": city_name,
                    "country": airport.country.name if airport.country else "Unknown",
                    "type": "airport",
                    "score": ratio,
                    "is_hub": 1 if code in self.SUPER_HUBS else 0,
                    "is_intl": 1 if airport.is_international else 0
                })
                seen_codes.add(code)

        def ranking_key(item):
            is_exact_iata = 1 if item['code'].lower() == query else 0
            return (-is_exact_iata, -item['is_hub'], -item['score'], -item['is_intl'], 0 if item['type'] == 'city' else 1)

        formatted_results.sort(key=ranking_key)
        
        final_results = []
        for res in formatted_results[:limit]:
            for k in ['score', 'is_hub', 'is_intl']:
                res.pop(k, None)
            final_results.append(res)

        if final_results:
            redis_helper.set_data_ttl(cache_key, final_results, self.cache_ttl)

        return final_results
