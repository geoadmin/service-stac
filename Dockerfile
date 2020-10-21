#############################################
# Base container with all necessary deps
# Buster slim python 3.7 base image.
FROM python:3.7-slim-buster as base
ENV HTTP_PORT 8080
RUN groupadd -r geoadmin && useradd -r -s /bin/false -g geoadmin geoadmin


# install relevent packages
RUN apt-get update \
    && apt-get install -y binutils libproj-dev gdal-bin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install pipenv \
    && pipenv --version

COPY Pipfile* /tmp/
RUN cd /tmp && \
    pipenv install --system --deploy

# Set the working dir and copy the app
WORKDIR /app
COPY --chown=geoadmin:geoadmin ./app /app/

#############################################
# Container to perform tests/management tasks
FROM base as test

RUN cd /tmp && \
    pipenv install --system --deploy --dev

WORKDIR /app
COPY ./wait-for-it.sh /app/

# for testing/management, settings.py just imports settings_dev
RUN echo "from .settings_dev import *" > /app/config/settings.py \
    && chown geoadmin:geoadmin /app/config/settings.py

# entrypoint is the manage command
ENTRYPOINT ["python3", "./manage.py"]


#############################################
# Container to use in production
FROM base as production

# on prod, settings.py just import settings_prod
RUN echo "from .settings_prod import *" > /app/config/settings.py \
    && chown geoadmin:geoadmin /app/config/settings.py

# Collect static files
RUN ./manage.py collectstatic --noinput

# production container must not run as root
USER geoadmin

EXPOSE $HTTP_PORT

# Use a real WSGI server
ENTRYPOINT ["python3", "./wsgi.py"]