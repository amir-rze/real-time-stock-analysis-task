from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import json
import logging
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException,Depends,Request,status,responses
from sqlalchemy.orm import Session
import uvicorn
from config import KAFKA_BOOTSTRAP_SERVERS,DATA_KAFKA_TOPIC,SIGNAL_KAFKA_TOPIC,HOST,PORT,REDIS_URL,MAX_REQUESTS_PER_MINUTE,BAN_DURATION
from models import Summary , Data
from database import Base , SessionLocal,engine
from schemas import SummaryOut, DataOut
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
import redis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from utils import convert_str_to_datetime , convert_datetime_to_str
from datetime import datetime , timedelta

logging.basicConfig(level=logging.INFO)


# Create the tables
Base.metadata.create_all(bind=engine)

# Create the Redis client
redis_client = redis.Redis.from_url(REDIS_URL)

def get_db() :
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


async def update_summary(data):
    db = SessionLocal()
    record = db.query(Summary).filter(Summary.stock_symbol == data['stock_symbol']).first()
    if record:
        if data['signal'] == 'Sell':
            record.sell_count += 1
        elif data['signal'] == 'Buy':
            record.buy_count += 1
        db.commit()
        logging.info("a record updated in Summary table ! ")
    else:
        # Create a new record
        new_record = Summary(stock_symbol=data['stock_symbol'], sell_count=0, buy_count=0)
        if data['signal'] == 'Sell':
            new_record.sell_count = 1
        elif data['signal'] == 'Buy':
            new_record.buy_count = 1
        db.add(new_record)
        db.commit()
        logging.info("new record added to Summary table ! ")
    return



async def create_data(data):
    db = SessionLocal()
    data['timestamp'] = convert_str_to_datetime(data['timestamp'])
    score = data['timestamp'].timestamp()
    db_data = Data(**data)
    db.add(db_data)
    db.commit()
    logging.info("New record added to Data table ! ")

    # Convert datetime to string in order to being serialized 
    data['timestamp'] = convert_datetime_to_str(data['timestamp'])
    # Add current data to redis 
    redis_client.zadd(f"data:{data['stock_symbol']}", {json.dumps(data): score})
    one_hour_ago = datetime.now() - timedelta(hours=1)
    # Remove records older than one hour
    redis_client.zremrangebyscore(f"data:{data['stock_symbol']}", 0, one_hour_ago.timestamp())
    logging.info("Data stored in Redis database ! ")

    return


# Read signal from 
async def read_signal():

    loop = asyncio.get_event_loop()
    consumer = AIOKafkaConsumer(
        SIGNAL_KAFKA_TOPIC,loop=loop,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    await consumer.start()
    try:
        async for message in consumer:
            data = message.value
            logging.info("Aggregation service received signal ! ")
            await update_summary(data)
    finally:
        await consumer.stop()

# Read data from Data Ingestion service
async def read_data():

    loop = asyncio.get_event_loop()
    consumer = AIOKafkaConsumer(
        DATA_KAFKA_TOPIC,loop=loop,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    await consumer.start()
    try:
        async for message in consumer:
            data = message.value
            logging.info("Aggregation service received data ! ")
            await create_data(data)
    finally:
        await consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(read_signal())
    asyncio.create_task(read_data())
    logging.info("Aggregation service received data !")    
    yield

app = FastAPI(lifespan=lifespan)

# Configure CORS
origins = [
    "*",  
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows specified origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Middleware for rate limiting
@app.middleware("http")
async def rate_limiting_middleware(request: Request, call_next):
    client_ip = request.client.host
    now = datetime.now()

    # Track the number of requests per IP
    request_count_key = f"request_count:{client_ip}"
    banned_key = f"banned:{client_ip}"

    # Check if IP is banned
    if redis_client.exists(banned_key):
        ban_end = datetime.strptime(redis_client.get(banned_key).decode(), "%Y-%m-%d %H:%M:%S")
        if ban_end > now:
            return responses.JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": "Too many requests, IP banned."})
        else:
            # Remove ban if time has passed
            redis_client.delete(banned_key)

    # Increment the request count
    request_count = redis_client.get(request_count_key)

    if request_count:
        request_count = int(request_count)
        if request_count >= MAX_REQUESTS_PER_MINUTE:
            # Ban the IP for a specific duration
            ban_end = (now + timedelta(minutes=BAN_DURATION)).strftime("%Y-%m-%d %H:%M:%S")
            redis_client.setex(banned_key, BAN_DURATION * 60, ban_end)
            return responses.JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS, content={"detail": "Too many requests, IP banned."})
        else:
            redis_client.incr(request_count_key)
    else:
        redis_client.setex(request_count_key, 60, 1)  # Expiry of 1 minute for request counting

    response = await call_next(request)
    return response



# retrieve the data for the past hour
@app.get("/data/", response_model=List[DataOut])
def get_latest_data(stock: str, db: Session = Depends(get_db)):
    # Fetch data for the specified stock_symbol from Redis
    data =  redis_client.zrange(f"data:{stock}", 0, -1)
    return [json.loads(d) for d in data]


@app.get("/summary/", response_model=List[SummaryOut])
async def get_summary(db: Session = Depends(get_db)):
    summaries = db.query(Summary).all()
    logging.info("Stock summary sent to client ! ")
    return summaries

FastAPICache.init(RedisBackend(redis_client), prefix="aggregation-service")


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
