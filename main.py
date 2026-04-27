# main.py
import logging
import uvicorn
from app import create_app
from config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

config = Config()
app = create_app(config=config)

if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port, reload=False)
