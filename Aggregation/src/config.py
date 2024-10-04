
import os
from dotenv import dotenv_values

config = dotenv_values()

if config.get('MODE') == 'local' :
    REDIS_URL = config.get('REDIS_URL')
    KAFKA_BOOTSTRAP_SERVERS = config.get('KAFKA_BOOTSTRAP_SERVERS')
    HOST = config.get('HOST')
    PORT = int(config.get('PORT'))

else:   # Container env
    REDIS_URL = os.getenv('REDIS_URL')
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS') 
    HOST = os.getenv('HOST')
    PORT = int(os.getenv('PORT'))

SIGNAL_KAFKA_TOPIC = "stock-signal"
DATA_KAFKA_TOPIC = "stock-data"

# Rate limiting settings
MAX_REQUESTS_PER_MINUTE = 60
BAN_DURATION = 120  # In minutes