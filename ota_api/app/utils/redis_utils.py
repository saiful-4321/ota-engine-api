from config import REDIS_HOST, REDIS_PORT, REDIS_PASS, REDIS_DB
import redis
import json
from contextlib import contextmanager

class RedisHelper:
    def __init__(self, host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASS, db=int(REDIS_DB)):
        self.host = host
        self.port = port
        self.password = password  # 🔹 Store password in self.password
        self.db = db
        self.redis_client = redis.StrictRedis(host=host, port=port, password=password, db=db)

    def get_redis_uri(self):
        """Generate the Redis URI based on connection details."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"

    def get_database_list(self):
        database_list = []
        for db_index in range(self.redis_client.dbsize()):
            try:
                self.redis_client.select(db_index)
                database_list.append(db_index)
            except redis.exceptions.ResponseError:
                pass

        return database_list
    
    @contextmanager
    def _with_db_context(self, db=None):
        original_db = self.db
        switched = False
        if db is not None and db != original_db:
            self.redis_client.select(db)
            switched = True
        try:
            yield self.redis_client
        finally:
            if switched:
                self.redis_client.select(original_db)

    def set_data(self, key, data, db=None):
        json_data = json.dumps(data)
        with self._with_db_context(db) as client:
            client.set(key, json_data)

    def set_data_ttl(self, key, data, ttl_minutes=60, db=None):
        json_data = json.dumps(data)
        with self._with_db_context(db) as client:
            client.set(key, json_data)
            client.expire(key, int(ttl_minutes * 60))

    def get_data(self, key, db=None):
        with self._with_db_context(db) as client:
            stored_data = client.get(key)
            if stored_data:
                return json.loads(stored_data.decode('utf-8'))
            else:
                return None

    def get_all_keys(self, db=None):
        with self._with_db_context(db) as client:
            return [key.decode('utf-8') for key in client.keys()]
    
    def get_all_key_value_data(self, db=None):
        with self._with_db_context(db) as client:
            keys = client.keys()
            result = {}
            for key_bytes in keys:
                key = key_bytes.decode('utf-8')
                try:
                    key_type = client.type(key_bytes)
                    ttl_seconds = client.ttl(key_bytes)
                    ttl_minutes = ttl_seconds // 60 if ttl_seconds >= 0 else ttl_seconds  # -1 for no expiry, -2 shouldn't occur here

                    if key_type == b'string':
                        value_bytes = client.get(key_bytes)
                        value = value_bytes.decode('utf-8') if value_bytes else None
                        result[key] = {
                            "type": "string",
                            "value": value,
                            "ttl_minutes": ttl_minutes
                        }
                    elif key_type == b'hash':
                        hash_data = client.hgetall(key_bytes)
                        value = {k.decode('utf-8'): v.decode('utf-8') for k, v in hash_data.items()}
                        result[key] = {
                            "type": "hash",
                            "value": value,
                            "ttl_minutes": ttl_minutes
                        }
                    elif key_type == b'list':
                        list_data = client.lrange(key_bytes, 0, -1)
                        value = [item.decode('utf-8') for item in list_data]
                        result[key] = {
                            "type": "list",
                            "value": value,
                            "ttl_minutes": ttl_minutes
                        }
                    elif key_type == b'set':
                        set_data = client.smembers(key_bytes)
                        value = [item.decode('utf-8') for item in set_data]
                        result[key] = {
                            "type": "set",
                            "value": value,
                            "ttl_minutes": ttl_minutes
                        }
                    elif key_type == b'zset':
                        zset_data = client.zrange(key_bytes, 0, -1, withscores=True)
                        value = [(member.decode('utf-8'), score) for member, score in zset_data]
                        result[key] = {
                            "type": "zset",
                            "value": value,
                            "ttl_minutes": ttl_minutes
                        }
                    else:
                        result[key] = {
                            "type": key_type.decode('utf-8'),
                            "value": None,
                            "ttl_minutes": ttl_minutes,
                            "note": "Unsupported type for value fetching"
                        }
                except Exception as e:
                    result[key] = {
                        "type": "error",
                        "value": None,
                        "ttl_minutes": -2,  # Indicate error
                        "error": str(e)
                    }
            return result

    def delete_key(self, key, db=None):
        with self._with_db_context(db) as client:
            return client.delete(key)
        
    def delete_key_value(self, key, expected_value, db=None):
        with self._with_db_context(db) as client:
            stored_data = client.get(key)
            if stored_data:
                current_value = json.loads(stored_data.decode('utf-8'))
                if current_value == expected_value:
                    client.delete(key)
                    return True
        return False
    
    def sadd(self, key, value, db=None):
        with self._with_db_context(db) as client:
            return client.sadd(key, value)

    def srem(self, key, value, db=None):
        with self._with_db_context(db) as client:
            return client.srem(key, value)

    def smembers(self, key, db=None):
        with self._with_db_context(db) as client:
            members = client.smembers(key)
            return [m.decode('utf-8') for m in members] if members else []

    def sismember(self, key, value, db=None):
        with self._with_db_context(db) as client:
            return bool(client.sismember(key, value))
    
    def delete_keys_pipeline(self, keys: list[str], db=None):
        """
        Delete multiple keys safely using Redis pipeline.
        - Non-blocking (UNLINK)
        - Best-effort (ignores missing / expired keys)
        """
        if not keys:
            return 0

        with self._with_db_context(db) as client:
            pipe = client.pipeline(transaction=False)
            redis_version = client.info()["redis_version"]
            major = int(redis_version.split(".")[0])
            if major >= 4:
                pipe.unlink(*keys)
            else:
                pipe.delete(*keys) 
            results = pipe.execute()
            return results[0] if results else 0
            
redis_helper = RedisHelper()