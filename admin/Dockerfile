FROM python:3.13-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY rct2-required-files.json .
COPY static ./static
ENV MOCK_MODE=true BRIDGE_HOST=127.0.0.1 BRIDGE_PORT=11754
EXPOSE 8088
CMD ["gunicorn","-b","0.0.0.0:8088","app:app","--workers","1","--threads","4"]
