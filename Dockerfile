FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir telethon openai pillow python-dotenv
COPY bot.py .
COPY chat_lister.py .
CMD ["python3", "-u", "bot.py"]
