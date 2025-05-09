###########################################################
# Container that contains basic configurations used by all other containers
# It should only contain variables that don't change or change very infrequently
# so that the cache is not needlessly invalidated
FROM python:3.12-slim-bullseye AS base
ENV HTTP_PORT=8080
ENV USER=geoadmin
ENV GROUP=geoadmin
ENV INSTALL_DIR=/opt/service-stac
ENV SRC_DIR=/usr/local/src/service-stac
ENV PIPENV_VENV_IN_PROJECT=1

RUN apt-get -qq update > /dev/null \
    && apt-get -qq -y install gdal-bin > /dev/null \
    && apt-get -qq clean \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r ${GROUP} \
    && useradd -r -s /bin/false -g ${GROUP} ${USER}

###########################################################
# Builder container
FROM base AS builder
RUN apt-get -qq update > /dev/null \
    && apt-get -qq -y install \
    # dev dependencies
    binutils libproj-dev \
    # silent the installation
    > /dev/null \
    && apt-get -qq clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install pipenv \
    && pipenv --version

COPY Pipfile.lock Pipfile ${SRC_DIR}/
RUN cd ${SRC_DIR} && pipenv sync

COPY --chown=${USER}:${GROUP} spec/ ${INSTALL_DIR}/spec/
COPY --chown=${USER}:${GROUP} app/ ${INSTALL_DIR}/app/

###########################################################
# Container to perform tests/management/dev tasks
FROM base AS debug
LABEL target=debug
ENV DEBUG=1

RUN apt-get -qq update > /dev/null \
    && apt-get -qq -y install \
    curl \
    net-tools \
    iputils-ping \
    postgresql-client-common \
    jq \
    openssh-client \
    binutils \
    libproj-dev \
    # silent the install
    > /dev/null \
    && apt-get -qq clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install pipenv \
    && pipenv --version

# Install all dev dependencies
COPY Pipfile.lock Pipfile ${INSTALL_DIR}/
RUN cd ${INSTALL_DIR} && pipenv sync --dev

# this is only used with the docker compose setup within CI
# to ensure that the app is only started once the DB container
# is ready
COPY ./wait-for-it.sh ${INSTALL_DIR}/app/

COPY --from=builder ${INSTALL_DIR}/ ${INSTALL_DIR}/
# on dev, settings.py needs to be replaced to import settings_dev
RUN echo "from .settings_dev import *" > ${INSTALL_DIR}/app/config/settings.py \
    && chown ${USER}:${GROUP} ${INSTALL_DIR}/app/config/settings.py

# Activate virtualenv
ENV VIRTUAL_ENV=${INSTALL_DIR}/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONHOME=""

# Overwrite the version.py from source with the actual version
ARG VERSION=unknown
RUN echo "APP_VERSION = '$VERSION'" > ${INSTALL_DIR}/app/config/version.py

# Collect static files.
# In theory for most development use, we should not need this. But it is
# sometimes useful to run a development build in Kubernetes, which requires the
# static files to be included. This also helps to reduce the difference between
# dev and prod and make troubleshooting easier.
# See also https://whitenoise.readthedocs.io/en/stable/django.html#using-whitenoise-in-development
# Some variables like AWS_ are mandatory so set them to avoid exceptions.
RUN LOGGING_CFG=0 \
    LEGACY_AWS_ACCESS_KEY_ID= \
    LEGACY_AWS_SECRET_ACCESS_KEY= \
    LEGACY_AWS_S3_BUCKET_NAME= \
    AWS_S3_BUCKET_NAME= \
    AWS_ROLE_ARN= \
    ${INSTALL_DIR}/app/manage.py collectstatic --noinput

ARG GIT_HASH=unknown
ARG GIT_BRANCH=unknown
ARG GIT_DIRTY=""
ARG AUTHOR=unknown
LABEL git.hash=$GIT_HASH
LABEL git.branch=$GIT_BRANCH
LABEL git.dirty="$GIT_DIRTY"
LABEL author=$AUTHOR
LABEL version=$VERSION

WORKDIR ${INSTALL_DIR}/app/
USER ${USER}

EXPOSE ${HTTP_PORT}
# entrypoint is the manage command
ENTRYPOINT ["python"]


###########################################################
# Container to use in production
FROM base AS production
LABEL target=production
ENV DEBUG=0

COPY --from=builder ${SRC_DIR}/.venv/ ${INSTALL_DIR}/.venv/

COPY --from=builder ${INSTALL_DIR}/ ${INSTALL_DIR}/
# on prod, settings.py needs to be replaced to import settings_prod instead of settings_dev
RUN echo "from .settings_prod import *" > ${INSTALL_DIR}/app/config/settings.py \
    && chown ${USER}:${GROUP} ${INSTALL_DIR}/app/config/settings.py

# Activate virtual environnment
ENV VIRTUAL_ENV=${INSTALL_DIR}/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONHOME=""

# Overwrite the version.py from source with the actual version
ARG VERSION=unknown
RUN echo "APP_VERSION = '$VERSION'" > ${INSTALL_DIR}/app/config/version.py

# Collect static files.
# Some variables like AWS_ are mandatory so set them to avoid exceptions.
RUN LOGGING_CFG=0 \
    LEGACY_AWS_ACCESS_KEY_ID= \
    LEGACY_AWS_SECRET_ACCESS_KEY= \
    LEGACY_AWS_S3_BUCKET_NAME= \
    AWS_S3_BUCKET_NAME= \
    AWS_ROLE_ARN= \
    ${INSTALL_DIR}/app/manage.py collectstatic --noinput

ARG GIT_HASH=unknown
ARG GIT_BRANCH=unknown
ARG GIT_DIRTY=""
ARG AUTHOR=unknown
LABEL git.hash=$GIT_HASH
LABEL git.branch=$GIT_BRANCH
LABEL git.dirty="$GIT_DIRTY"
LABEL author=$AUTHOR
LABEL version=$VERSION
# production container must not run as root
WORKDIR ${INSTALL_DIR}/app/
USER ${USER}

EXPOSE ${HTTP_PORT}
# entrypoint is the manage command
ENTRYPOINT ["python"]
