# Buster slim python 3.7 base image.
FROM python:3.7-slim-buster
ENV HTTP_PORT 8080
RUN groupadd -r geoadmin && useradd -r -s /bin/false -g geoadmin geoadmin


# install relevent packages
RUN apt-get update && apt-get install -y binutils libproj-dev gdal-bin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY "./requirements.txt" "/app/requirements.txt"

RUN pip3 install -r requirements.txt

COPY --chown=geoadmin:geoadmin "./" "/app/"

USER geoadmin

EXPOSE $HTTP_PORT

# Use a real WSGI server
ENTRYPOINT ["python3", "./project/wsgi.py"]
