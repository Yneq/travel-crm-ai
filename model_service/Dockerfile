FROM python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
WORKDIR /app
COPY model_service/requirements.lock.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY model_service ./model_service
RUN useradd --uid 10001 --create-home modeluser && mkdir /cache && chown modeluser /cache
USER 10001
ENV HF_HOME=/cache CPU_THREADS=2
EXPOSE 8090
CMD ["uvicorn", "model_service.app:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1"]
