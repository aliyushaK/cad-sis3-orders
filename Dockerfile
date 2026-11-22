# Base image from ECR Public (avoids Docker Hub rate limits in CI)
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .

# do not run as root inside the container
RUN useradd --system --uid 10001 appuser
USER appuser

EXPOSE 8080
CMD ["python", "app.py"]
