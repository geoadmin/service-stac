###########################################################
# Base container with all necessary deps
# Buster slim python 3.7 base image.
FROM python:3.7-slim-buster as base
ENV HTTP_PORT 8080
RUN groupadd -r geoadmin && useradd -r -s /bin/false -g geoadmin geoadmin


# install relevent packages
RUN apt-get update \
    && apt-get install -y binutils libproj-dev gdal-bin \
    # the following line contains debug tools that can be removed later
    curl net-tools iputils-ping postgresql-client-common jq openssh-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install pipenv \
    && pipenv --version

COPY Pipfile* /tmp/
RUN cd /tmp && \
    pipenv install --system --deploy --ignore-pipfile

# Set the working dir and copy the app
WORKDIR /app
COPY --chown=geoadmin:geoadmin ./app /app/
COPY --chown=geoadmin:geoadmin ./spec /spec/

###########################################################
# Container to perform tests/management/dev tasks
FROM base as debug

RUN cd /tmp && \
    pipenv install --system --deploy --ignore-pipfile --dev

# this is only used with the docker-compose setup within CI
# to ensure that the app is only started once the DB container
# is ready
COPY ./wait-for-it.sh /app/

# for testing/management, settings.py just imports settings_dev
RUN echo "from .settings_dev import *" > /app/config/settings.py \
    && chown geoadmin:geoadmin /app/config/settings.py

# NOTE: uses a dummy secret_key to avoid django raising settings error
RUN SECRET_KEY=dummy ./manage.py collectstatic --noinput

USER geoadmin

EXPOSE $HTTP_PORT

# entrypoint is the manage command
ENTRYPOINT ["python3"]


###########################################################
# Container to use in production
FROM base as production

# on prod, settings.py just import settings_prod
RUN echo "from .settings_prod import *" > /app/config/settings.py \
    && chown geoadmin:geoadmin /app/config/settings.py

# Collect static files, uses a dummy secret_key to avoid django raising settings error
RUN SECRET_KEY=dummy ./manage.py collectstatic --noinput

# production container must not run as root
USER geoadmin

EXPOSE $HTTP_PORT

# Use a real WSGI server
ENTRYPOINT ["python3"]