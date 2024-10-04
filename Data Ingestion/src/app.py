from fastapi import FastAPI,Depends,status,Response
from fastapi.middleware.cors import CORSMiddleware
import json
from typing import List,Union
from aiokafka import AIOKafkaProducer
import logging
import uvicorn
from config import KAFKA_BOOTSTRAP_SERVERS,DATA_KAFKA_TOPIC,ADDITIONAL_DATA_KAFTA_TOPIC,HOST,PORT
from schemas import DataIn,AdditionalDataInEconomic,AdditionalDataInMarket,AdditionalDataInNews,AdditionalDataInOrder
from utils import convert_datetime_to_str,convert_utc_to_Tehran
import asyncio


app = FastAPI()


origins = ["http://localhost", "http://127.0.0.1"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows only localhost
    allow_credentials=True,
    allow_methods=["POST"],  # Allow only POST (or restrict to necessary methods)
    allow_headers=["*"],  # Allows all headers
)
logging.basicConfig(level=logging.INFO)

# Define the Kafka producer
async def send_data(data,topic):
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,loop=asyncio.get_event_loop(),
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
    await producer.start()
    try:
        await producer.send(topic, value=data)
        logging.info("data or additional-data sent to stream processing service successfully...")
    except Exception as e:
        logging.error("Failed to send data or additional data")
    finally: 
        await producer.stop()



# Define the route to receive the data
@app.post("/ingest/",status_code=status.HTTP_200_OK)
async def ingest_data(
     data: Union[DataIn, AdditionalDataInOrder, AdditionalDataInNews, AdditionalDataInMarket, AdditionalDataInEconomic],response:Response):
    
    if isinstance(data, DataIn):

        data=dict(data)
        # Convert datetime to Asia/Tehran time
        data['timestamp'] = convert_utc_to_Tehran(data['timestamp'])
        data['timestamp'] = convert_datetime_to_str(data['timestamp'])
        # Send data to Stream Processing Service
        await send_data(data,DATA_KAFKA_TOPIC)
        return {"message": "Data ingested successfully"}
       
    elif isinstance(data, AdditionalDataInOrder) or isinstance(data, AdditionalDataInNews)\
            or isinstance(data, AdditionalDataInMarket) or isinstance(data, AdditionalDataInEconomic) :
        data = dict(data)
        # Convert datetime to Asia/Tehran time
        data['timestamp'] = convert_datetime_to_str(data['timestamp'])

        # Send additional-data to Trading Signal service directly 
        await send_data(data,ADDITIONAL_DATA_KAFTA_TOPIC)

        return {"message": "Additional Data ingested successfully"}
    else:
        response.status_code = status.HTTP_400_BAD_REQUEST
        return { "message": "Data is not valid!"}



if __name__ == "__main__":
    uvicorn.run('app:app', host=HOST, port=PORT)