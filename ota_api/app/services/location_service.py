from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.otadb.Airport import Airport
from app.models.otadb.City import City
from app.models.otadb.Country import Country
from app.utils.redis_utils import redis_helper
import hashlib

class LocationService:
    def __init__(self, db: Session):
        self.db = db
        self.cache_ttl = 3600  # Cache results for 1 hour

    def search_locations(self, query: str, limit: int = 15):
        if not query:
            return []

        query = query.strip().lower()
        
        # 1. Check Redis Cache First
        cache_key = f"loc_search:{hashlib.md5(query.encode()).hexdigest()}"
        cached_results = redis_helper.get_data(cache_key)
        if cached_results:
            return cached_results

        # 2. Database Search
        search_term = f"%{query}%"

        # Search Cities (Priority 1)
        city_results = (
            self.db.query(City)
            .outerjoin(Country, City.country_id == Country.id)
            .filter(City.status == 'Active')
            .filter(
                or_(
                    City.name.ilike(search_term),
                    City.iata_code.ilike(query)
                )
            )
            .limit(limit)
            .all()
        )

        # Search Individual Airports (Priority 2)
        airport_results = (
            self.db.query(Airport)
            .outerjoin(City, Airport.city_id == City.id)
            .outerjoin(Country, Airport.country_id == Country.id)
            .filter(Airport.status == 'Active')
            .filter(
                or_(
                    Airport.iata_code.ilike(query),
                    Airport.name.ilike(search_term)
                )
            )
            .limit(limit)
            .all()
        )

        formatted_results = []
        seen_codes = set()

        # Format Cities
        for city in city_results:
            code = city.iata_code or ""
            if code and code not in seen_codes:
                formatted_results.append({
                    "code": code,
                    "name": "All Airports",
                    "city": city.name or "Unknown",
                    "country": city.country.name if city.country else "Unknown",
                    "type": "city"
                })
                seen_codes.add(code)

        # Format Airports
        for airport in airport_results:
            code = airport.iata_code or ""
            if code and code not in seen_codes:
                formatted_results.append({
                    "code": code,
                    "name": airport.name or "Unknown",
                    "city": airport.city.name if airport.city else "Unknown",
                    "country": airport.country.name if airport.country else "Unknown",
                    "type": "airport"
                })
                seen_codes.add(code)

        # 3. Intelligent Ranking Logic
        def relevance_score(item):
            code_lower = (item['code'] or "").lower()
            city_lower = (item['city'] or "").lower()
            name_lower = (item['name'] or "").lower()
            
            if code_lower == query:
                return (0, item['type'] != 'city')
            if city_lower.startswith(query):
                return (1, item['type'] != 'city')
            if name_lower.startswith(query):
                return (2, item['type'] != 'city')
            return (3, item['type'] != 'city')

        formatted_results.sort(key=relevance_score)
        final_results = formatted_results[:limit]

        # 4. Save to Cache
        if final_results:
            redis_helper.set_data_ttl(cache_key, final_results, self.cache_ttl)

        return final_results
