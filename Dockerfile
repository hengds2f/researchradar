FROM python:3.11

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face runs Spaces on port 7860
EXPOSE 7860

CMD ["python", "app.py"]
