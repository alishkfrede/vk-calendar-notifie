from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import router
from app.database import init_db
from app.utils.logger import log
from app.services.vk_longpoll import longpoll_service
from app.services.scheduler_service import scheduler_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Инициализация БД...")
    init_db()
    log.info("БД готова.")
    
    # Запускаем VK LongPoll
    log.info("Запуск VK LongPoll...")
    longpoll_service.start()
    
    # Запускаем планировщик задач
    log.info("Запуск планировщика задач...")
    scheduler_service.start()
    
    yield
    
    # Останавливаем сервисы при завершении
    log.info("Остановка VK LongPoll...")
    longpoll_service.stop()
    
    log.info("Остановка планировщика...")
    scheduler_service.stop()
    
    log.info("Завершение работы.")


app = FastAPI(
    title="VK Calendar Notifier",
    version="1.0",
    lifespan=lifespan,
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)