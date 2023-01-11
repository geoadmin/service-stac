###########################################################
# Container that contains basic configurations used by all other containers
# It should only contain variables that don't change or change very infrequently
# so that the cache is not needlessly invalidated
FROM python:3.9-slim-bullseye as base
ENV HTTP_PORT=8080
ENV USER=geoadmin
ENV GROUP=geoadmin
ENV INSTALL_DIR=/opt/service-stac
ENV SRC_DIR=/usr/local/src/service-stac
ENV PIPENV_VENV_IN_PROJECT=1

RUN groupadd -r ${GROUP} \
    && useradd -r -s /bin/false -g ${GROUP} ${USER} \
    && mkdir -p ${INSTALL_DIR}/logs && chown ${USER}:${GROUP} ${INSTALL_DIR}/logs

EXPOSE $HTTP_PORT
# entrypoint is the manage command
ENTRYPOINT ["python"]

###########################################################
# Container to perform tests/management/dev tasks
FROM base as debug
LABEL target=debug
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y gdal-bin \
    # dev dependencies
    binutils libproj-dev \
    # debug tools
    curl net-tools iputils-ping postgresql-client-common jq openssh-client \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install pipenv \
    && pipenv --version

COPY Pipfile.lock Pipfile ${INSTALL_DIR}/
RUN cd ${INSTALL_DIR} && pipenv sync --dev

# this is only used with the docker-compose setup within CI
# to ensure that the app is only started once the DB container
# is ready
COPY ./wait-for-it.sh ${INSTALL_DIR}/app/

# Is it safe for the executable files to be writable by the user who executes them? (At a first
# glance, it seems to also work without this chown, but as I am not sure why this was added I left
# it like this for the moment)
COPY --chown=${USER}:${GROUP} .env.default ${INSTALL_DIR}/
COPY --chown=${USER}:${GROUP} spec/ ${INSTALL_DIR}/spec/
COPY --chown=${USER}:${GROUP} app/ ${INSTALL_DIR}/app/

# Activate virtualenv
ENV VIRTUAL_ENV=${INSTALL_DIR}/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONHOME=""

# Overwrite the version.py from source with the actual version
ARG VERSION=unknown
RUN echo "APP_VERSION = '$VERSION'" > ${INSTALL_DIR}/app/config/version.py

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

###########################################################
# Builder container
FROM base as builder
RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y gdal-bin \
    # dev dependencies
    binutils libproj-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install pipenv \
    && pipenv --version

COPY Pipfile.lock Pipfile ${SRC_DIR}/
RUN cd ${SRC_DIR} && pipenv sync

COPY --chown=${USER}:${GROUP} .env.default ${INSTALL_DIR}/
COPY --chown=${USER}:${GROUP} spec/ ${INSTALL_DIR}/spec/
COPY --chown=${USER}:${GROUP} app/ ${INSTALL_DIR}/app/

# on prod, settings.py needs to be replaced to import settings_prod instead of settings_dev
RUN echo "from .settings_prod import *" > ${INSTALL_DIR}/app/config/settings.py \
    && chown ${USER}:${GROUP} ${INSTALL_DIR}/app/config/settings.py


###########################################################
# Container to use in production
FROM base as production
LABEL target=production

RUN apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y gdal-bin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder ${INSTALL_DIR}/ ${INSTALL_DIR}/
COPY --from=builder ${SRC_DIR}/.venv/ ${INSTALL_DIR}/.venv/

# Activate virtual environnment
ENV VIRTUAL_ENV=${INSTALL_DIR}/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONHOME=""

# Overwrite the version.py from source with the actual version
ARG VERSION=unknown
RUN echo "APP_VERSION = '$VERSION'" > ${INSTALL_DIR}/app/config/version.py

# Collect static files, uses the .env.default settings to avoid django raising settings error
RUN APP_ENV=default LOGGING_CFG=0 ${INSTALL_DIR}/app/manage.py collectstatic --noinput

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
