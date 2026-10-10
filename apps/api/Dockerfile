FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY requirements.txt requirements.lock ./
COPY apps/api/requirements.txt apps/api/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api apps/api
WORKDIR /workspace/apps/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
