FROM python:3.12-slim

# Tesseract + חבילת העברית. pdfplumber ממיר עמודים לתמונה בעצמו (pypdfium2), ולכן לא צריך Poppler.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-heb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# docker build -t attendance .
# docker run --rm -v "%cd%/data:/app/data" attendance            (Windows CMD)
# docker run --rm -v "$(pwd)/data:/app/data" attendance           (Linux / Mac / Git Bash)
ENTRYPOINT ["python", "main.py"]
